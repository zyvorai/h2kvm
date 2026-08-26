// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package api

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"log"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/msteinert/pam/v2"
)

// SessionStore manages authenticated sessions.
type SessionStore struct {
	mu       sync.RWMutex
	sessions map[string]*sessionData
}

type sessionData struct {
	Username  string    `json:"username"`
	CreatedAt time.Time `json:"created_at"`
}

// NewSessionStore creates an empty session store.
func NewSessionStore() *SessionStore {
	return &SessionStore{
		sessions: make(map[string]*sessionData),
	}
}

// CreateSession generates a random token and stores the session.
func (s *SessionStore) CreateSession(username string) string {
	tokenBytes := make([]byte, 32)
	rand.Read(tokenBytes)
	token := hex.EncodeToString(tokenBytes)

	s.mu.Lock()
	s.sessions[token] = &sessionData{
		Username:  username,
		CreatedAt: time.Now(),
	}
	s.mu.Unlock()

	return token
}

// ValidateSession returns the username if the token is valid.
func (s *SessionStore) ValidateSession(token string) (string, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	sess, ok := s.sessions[token]
	if !ok {
		return "", false
	}
	return sess.Username, true
}

// RemoveSession deletes a session.
func (s *SessionStore) RemoveSession(token string) {
	s.mu.Lock()
	delete(s.sessions, token)
	s.mu.Unlock()
}

// pamAuthenticate verifies credentials against system PAM.
func pamAuthenticate(username, password string) error {
	t, err := pam.StartFunc("login", username,
		func(style pam.Style, msg string) (string, error) {
			switch style {
			case pam.PromptEchoOff:
				return password, nil
			case pam.PromptEchoOn:
				return username, nil
			default:
				return "", nil
			}
		})
	if err != nil {
		return err
	}
	defer t.End()

	return t.Authenticate(0)
}

// --- Login rate limiting ---

// loginAttempt tracks failed login attempts for a single IP.
type loginAttempt struct {
	Count    int
	FirstAt  time.Time
}

const (
	loginRateMaxAttempts = 5
	loginRateWindow      = 5 * time.Minute
)

var (
	loginRateMu sync.Mutex
	loginRates  = make(map[string]*loginAttempt)
)

// checkLoginRate returns true if the IP has exceeded the rate limit.
func checkLoginRate(ip string) bool {
	loginRateMu.Lock()
	defer loginRateMu.Unlock()

	attempt, ok := loginRates[ip]
	if !ok {
		return false
	}

	// Window expired -- reset.
	if time.Since(attempt.FirstAt) > loginRateWindow {
		delete(loginRates, ip)
		return false
	}

	return attempt.Count >= loginRateMaxAttempts
}

// recordLoginFailure increments the failure counter for an IP.
func recordLoginFailure(ip string) {
	loginRateMu.Lock()
	defer loginRateMu.Unlock()

	attempt, ok := loginRates[ip]
	if !ok || time.Since(attempt.FirstAt) > loginRateWindow {
		loginRates[ip] = &loginAttempt{Count: 1, FirstAt: time.Now()}
		log.Printf("[auth] login failure recorded ip=%s count=1", ip)
		return
	}
	attempt.Count++
	log.Printf("[auth] login failure recorded ip=%s count=%d/%d", ip, attempt.Count, loginRateMaxAttempts)
	if attempt.Count >= loginRateMaxAttempts {
		log.Printf("[auth] rate limit TRIGGERED ip=%s (blocked for %s)", ip, loginRateWindow)
	}
}

// resetLoginRate clears the failure counter on successful login.
func resetLoginRate(ip string) {
	loginRateMu.Lock()
	delete(loginRates, ip)
	loginRateMu.Unlock()
}

// --- HTTP Handlers ---

type loginRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

func (s *Server) handleLogin(w http.ResponseWriter, r *http.Request) {
	// Rate limiting: block IPs with too many failed attempts.
	clientIP := r.RemoteAddr
	if fwd := r.Header.Get("X-Real-Ip"); fwd != "" {
		clientIP = fwd
	}
	if checkLoginRate(clientIP) {
		log.Printf("[auth] rate limited login attempt from %s", clientIP)
		jsonError(w, http.StatusTooManyRequests, "too many failed login attempts; try again later")
		return
	}

	var req loginRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		jsonError(w, http.StatusBadRequest, "invalid request")
		return
	}

	if req.Username == "" || req.Password == "" {
		jsonError(w, http.StatusBadRequest, "username and password required")
		return
	}

	// Validate username characters.
	for _, c := range req.Username {
		if !((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.') {
			jsonError(w, http.StatusBadRequest, "invalid username characters")
			return
		}
	}

	if err := pamAuthenticate(req.Username, req.Password); err != nil {
		log.Printf("[auth] login FAILED user=%s ip=%s error=%v", req.Username, clientIP, err)
		recordLoginFailure(clientIP)
		jsonError(w, http.StatusUnauthorized, "invalid username or password")
		return
	}

	log.Printf("[auth] login SUCCESS user=%s ip=%s", req.Username, clientIP)
	resetLoginRate(clientIP)
	token := s.sessions.CreateSession(req.Username)

	http.SetCookie(w, s.sessionCookie("h2kweb_session", token, 0))

	jsonResponse(w, http.StatusOK, map[string]string{
		"status":   "ok",
		"username": req.Username,
	})
}

func (s *Server) handleLogout(w http.ResponseWriter, r *http.Request) {
	if token := extractSessionToken(r); token != "" {
		if username, ok := s.sessions.ValidateSession(token); ok {
			log.Printf("[auth] logout user=%s ip=%s", username, r.RemoteAddr)
		}
		s.sessions.RemoveSession(token)
	}

	http.SetCookie(w, s.sessionCookie("h2kweb_session", "", -1))

	jsonResponse(w, http.StatusOK, map[string]string{"status": "logged_out"})
}

func (s *Server) handleSession(w http.ResponseWriter, r *http.Request) {
	token := extractSessionToken(r)
	if token == "" {
		log.Printf("[auth] session check: no token, ip=%s", r.RemoteAddr)
		jsonResponse(w, http.StatusUnauthorized, map[string]interface{}{
			"authenticated": false,
		})
		return
	}

	username, ok := s.sessions.ValidateSession(token)
	if !ok {
		log.Printf("[auth] session check: invalid token, ip=%s", r.RemoteAddr)
		jsonResponse(w, http.StatusUnauthorized, map[string]interface{}{
			"authenticated": false,
		})
		return
	}

	jsonResponse(w, http.StatusOK, map[string]interface{}{
		"authenticated": true,
		"username":      username,
	})
}

// --- Middleware ---

// authRequired protects routes — checks session cookie.
// Skips: /api/v1/auth/*, /api/v1/health, static files.
func (s *Server) authRequired(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path := r.URL.Path

		// Public endpoints + WebSocket paths (auth validated before modal opens).
		if path == "/api/v1/health" ||
			path == "/metrics" ||
			strings.HasPrefix(path, "/api/v1/auth/") ||
			strings.HasPrefix(path, "/api/v1/vnc-proxy/") ||
			strings.HasPrefix(path, "/api/v1/vnc-proxy-kv/") ||
			strings.HasPrefix(path, "/api/v1/ws") ||
			!strings.HasPrefix(path, "/api/") {
			next.ServeHTTP(w, r)
			return
		}

		// Check session cookie.
		token := extractSessionToken(r)
		if token != "" {
			if _, ok := s.sessions.ValidateSession(token); ok {
				next.ServeHTTP(w, r)
				return
			}
		}

		// Check API key header (fallback for CLI/scripts).
		if s.apiKey != "" {
			key := r.Header.Get("X-API-Key")
			if key == s.apiKey {
				next.ServeHTTP(w, r)
				return
			}
		}

		jsonError(w, http.StatusUnauthorized, "authentication required")
	})
}

// sessionCookie builds a session cookie; Secure is set when serving over TLS.
func (s *Server) sessionCookie(name, value string, maxAge int) *http.Cookie {
	cookie := &http.Cookie{
		Name:     name,
		Value:    value,
		Path:     "/",
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   maxAge,
	}
	if s.tlsCert != "" {
		cookie.Secure = true
	}
	return cookie
}

// extractSessionToken gets the session token from cookie.
func extractSessionToken(r *http.Request) string {
	cookie, err := r.Cookie("h2kweb_session")
	if err != nil {
		return ""
	}
	return cookie.Value
}
