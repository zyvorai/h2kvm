# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/core/vmcraft/app_framework_detector.py
"""
Application framework and runtime detection.

Provides comprehensive application framework analysis:
- Python apps (virtualenv, pipenv, poetry, requirements.txt, Django, Flask)
- Node.js apps (package.json, npm, yarn, Express, React, Vue)
- Java apps (Maven, Gradle, WAR files, Spring Boot, Tomcat apps)
- PHP apps (composer.json, Laravel, Symfony, WordPress, Drupal)
- Ruby apps (Gemfile, Rails, Sinatra)
- Go apps (go.mod, go binaries)
- .NET apps (dotnet, ASP.NET)

Features:
- Detect application frameworks
- Parse dependency files
- Identify web frameworks
- List installed packages
- Version detection
"""

# pylint: disable=duplicate-code
# reason: this module has 5 near-identical "for search_path in
# search_paths: ... file_ops.find(...)" scan loops (one per language/
# framework detector) that are structurally similar to search-path scans
# in sibling vmcraft modules (e.g. database_detector.py,
# certificate_manager.py) by coincidence, not shared logic; keeping each
# independently editable avoids coupling unrelated per-framework detection
# code paths. See git history for the pylint pass that reviewed each
# instance.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base_analyzer import BaseAnalyzer


class AppFrameworkDetector(BaseAnalyzer):
    """
    Application framework and runtime detector.

    Detects programming languages, frameworks, and applications.
    """

    def detect_frameworks(self) -> dict[str, Any]:
        """
        Detect application frameworks comprehensively.

        Returns:
            Framework detection results
        """
        frameworks: dict[str, Any] = {
            "python": [],
            "nodejs": [],
            "java": [],
            "php": [],
            "ruby": [],
            "go": [],
            "dotnet": [],
            "total_apps": 0,
        }

        # Detect Python apps
        python_apps = self._detect_python_apps()
        frameworks["python"] = python_apps
        frameworks["total_apps"] += len(python_apps)

        # Detect Node.js apps
        nodejs_apps = self._detect_nodejs_apps()
        frameworks["nodejs"] = nodejs_apps
        frameworks["total_apps"] += len(nodejs_apps)

        # Detect Java apps
        java_apps = self._detect_java_apps()
        frameworks["java"] = java_apps
        frameworks["total_apps"] += len(java_apps)

        # Detect PHP apps
        php_apps = self._detect_php_apps()
        frameworks["php"] = php_apps
        frameworks["total_apps"] += len(php_apps)

        # Detect Ruby apps
        ruby_apps = self._detect_ruby_apps()
        frameworks["ruby"] = ruby_apps
        frameworks["total_apps"] += len(ruby_apps)

        # Detect Go apps
        go_apps = self._detect_go_apps()
        frameworks["go"] = go_apps
        frameworks["total_apps"] += len(go_apps)

        # Detect .NET apps
        dotnet_apps = self._detect_dotnet_apps()
        frameworks["dotnet"] = dotnet_apps
        frameworks["total_apps"] += len(dotnet_apps)

        return frameworks

    def _detect_python_apps(self) -> list[dict[str, Any]]:
        """Detect Python applications."""
        apps = []

        # Search common Python app locations
        search_paths = [
            "/opt",
            "/var/www",
            "/usr/local",
            "/home",
        ]

        for search_path in search_paths:
            if not self.file_ops.is_dir(search_path):
                continue

            try:
                # Find requirements.txt, setup.py, pyproject.toml
                files = self.file_ops.find(search_path)
                for file in files[:200]:  # Limit search
                    if file.endswith("requirements.txt"):
                        app_info = self._analyze_python_requirements(file)
                        if app_info:
                            apps.append(app_info)
                    elif file.endswith("pyproject.toml"):
                        app_info = self._analyze_python_pyproject(file)
                        if app_info:
                            apps.append(app_info)
                    elif file.endswith("manage.py"):
                        # Django app
                        apps.append(
                            {
                                "path": str(Path(file).parent),
                                "framework": "Django",
                                "type": "web",
                            }
                        )
                    elif "app.py" in file or "wsgi.py" in file:
                        # Flask/WSGI app
                        apps.append(
                            {
                                "path": str(Path(file).parent),
                                "framework": "Flask/WSGI",
                                "type": "web",
                            }
                        )

                    if len(apps) >= 20:  # Limit results
                        break

            except Exception as e:  # pylint: disable=broad-exception-caught
                # reason: best-effort app-framework detection scan; a guest fs read error on
                # one path/file must not abort detection of other frameworks
                self.logger.debug(f"Failed to search {search_path}: {e}")

        return apps

    def _analyze_python_requirements(self, requirements_file: str) -> dict[str, Any] | None:
        """Analyze Python requirements.txt."""
        try:
            content = self.file_ops.cat(requirements_file)
            packages = []

            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Extract package name
                if "==" in line:
                    pkg_name = line.split("==")[0]
                elif ">=" in line:
                    pkg_name = line.split(">=")[0]
                else:
                    pkg_name = line

                packages.append(pkg_name.strip())

            # Detect framework from packages
            framework = None
            if "django" in [p.lower() for p in packages]:
                framework = "Django"
            elif "flask" in [p.lower() for p in packages]:
                framework = "Flask"
            elif "fastapi" in [p.lower() for p in packages]:
                framework = "FastAPI"

            return {
                "path": str(Path(requirements_file).parent),
                "framework": framework or "Python",
                "type": "requirements.txt",
                "package_count": len(packages),
                "packages": packages[:10],  # Top 10
            }
        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort app-framework detection scan; a guest fs read error on
            # one path/file must not abort detection of other frameworks
            return None

    def _analyze_python_pyproject(self, pyproject_file: str) -> dict[str, Any] | None:
        """Analyze Python pyproject.toml."""
        try:
            self.file_ops.cat(pyproject_file)
            # Basic parsing (full TOML parsing would need library)

            return {
                "path": str(Path(pyproject_file).parent),
                "framework": "Python (Poetry/PDM)",
                "type": "pyproject.toml",
            }
        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort app-framework detection scan; a guest fs read error on
            # one path/file must not abort detection of other frameworks
            return None

    def _detect_nodejs_apps(self) -> list[dict[str, Any]]:
        """Detect Node.js applications."""
        apps = []

        search_paths = ["/opt", "/var/www", "/usr/local", "/home"]

        for search_path in search_paths:
            if not self.file_ops.is_dir(search_path):
                continue

            try:
                files = self.file_ops.find(search_path)
                for file in files[:200]:
                    if file.endswith("package.json"):
                        app_info = self._analyze_package_json(file)
                        if app_info:
                            apps.append(app_info)

                    if len(apps) >= 20:
                        break

            except Exception as e:  # pylint: disable=broad-exception-caught
                # reason: best-effort app-framework detection scan; a guest fs read error on
                # one path/file must not abort detection of other frameworks
                self.logger.debug(f"Failed to search {search_path}: {e}")

        return apps

    def _analyze_package_json(self, package_file: str) -> dict[str, Any] | None:
        """Analyze Node.js package.json."""
        try:
            content = self.file_ops.cat(package_file)
            pkg = json.loads(content)

            dependencies = pkg.get("dependencies", {})
            dev_dependencies = pkg.get("devDependencies", {})
            all_deps = {**dependencies, **dev_dependencies}

            # Detect framework
            framework = None
            if "express" in all_deps:
                framework = "Express.js"
            elif "react" in all_deps or "react-dom" in all_deps:
                framework = "React"
            elif "vue" in all_deps:
                framework = "Vue.js"
            elif "next" in all_deps:
                framework = "Next.js"
            elif "@angular/core" in all_deps:
                framework = "Angular"

            return {
                "path": str(Path(package_file).parent),
                "framework": framework or "Node.js",
                "type": "package.json",
                "name": pkg.get("name", "unknown"),
                "version": pkg.get("version", "unknown"),
                "dependency_count": len(all_deps),
            }
        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort app-framework detection scan; a guest fs read error on
            # one path/file must not abort detection of other frameworks
            return None

    def _detect_java_apps(self) -> list[dict[str, Any]]:
        """Detect Java applications."""
        apps = []

        # Look for WAR files
        search_paths = ["/opt", "/var/lib/tomcat", "/usr/local"]

        for search_path in search_paths:
            if not self.file_ops.is_dir(search_path):
                continue

            try:
                files = self.file_ops.find(search_path)
                for file in files[:100]:
                    if file.endswith(".war"):
                        apps.append(
                            {
                                "path": file,
                                "framework": "Java Web App",
                                "type": "WAR",
                            }
                        )
                    elif file.endswith("pom.xml"):
                        apps.append(
                            {
                                "path": str(Path(file).parent),
                                "framework": "Maven",
                                "type": "pom.xml",
                            }
                        )
                    elif file.endswith("build.gradle"):
                        apps.append(
                            {
                                "path": str(Path(file).parent),
                                "framework": "Gradle",
                                "type": "build.gradle",
                            }
                        )

                    if len(apps) >= 20:
                        break

            except Exception as e:  # pylint: disable=broad-exception-caught
                # reason: best-effort app-framework detection scan; a guest fs read error on
                # one path/file must not abort detection of other frameworks
                self.logger.debug(f"Failed to search {search_path}: {e}")

        return apps

    def _detect_php_apps(self) -> list[dict[str, Any]]:
        """Detect PHP applications."""
        apps = []

        search_paths = ["/var/www", "/usr/share", "/opt"]

        for search_path in search_paths:
            if not self.file_ops.is_dir(search_path):
                continue

            try:
                files = self.file_ops.find(search_path)
                for file in files[:200]:
                    if file.endswith("composer.json"):
                        app_info = self._analyze_composer_json(file)
                        if app_info:
                            apps.append(app_info)
                    elif "wp-config.php" in file:
                        apps.append(
                            {
                                "path": str(Path(file).parent),
                                "framework": "WordPress",
                                "type": "CMS",
                            }
                        )
                    elif "sites/default/settings.php" in file:
                        apps.append(
                            {
                                "path": str(Path(file).parent.parent.parent),
                                "framework": "Drupal",
                                "type": "CMS",
                            }
                        )

                    if len(apps) >= 20:
                        break

            except Exception as e:  # pylint: disable=broad-exception-caught
                # reason: best-effort app-framework detection scan; a guest fs read error on
                # one path/file must not abort detection of other frameworks
                self.logger.debug(f"Failed to search {search_path}: {e}")

        return apps

    def _analyze_composer_json(self, composer_file: str) -> dict[str, Any] | None:
        """Analyze PHP composer.json."""
        try:
            content = self.file_ops.cat(composer_file)
            composer = json.loads(content)

            require = composer.get("require", {})

            # Detect framework
            framework = None
            if "laravel/framework" in require:
                framework = "Laravel"
            elif "symfony/symfony" in require:
                framework = "Symfony"

            return {
                "path": str(Path(composer_file).parent),
                "framework": framework or "PHP (Composer)",
                "type": "composer.json",
                "name": composer.get("name", "unknown"),
                "dependency_count": len(require),
            }
        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort app-framework detection scan; a guest fs read error on
            # one path/file must not abort detection of other frameworks
            return None

    def _detect_ruby_apps(self) -> list[dict[str, Any]]:
        """Detect Ruby applications."""
        apps = []

        search_paths = ["/opt", "/var/www", "/home"]

        for search_path in search_paths:
            if not self.file_ops.is_dir(search_path):
                continue

            try:
                files = self.file_ops.find(search_path)
                for file in files[:200]:
                    if file.endswith("Gemfile"):
                        app_info = self._analyze_gemfile(file)
                        if app_info:
                            apps.append(app_info)
                    elif file.endswith("config.ru"):
                        apps.append(
                            {
                                "path": str(Path(file).parent),
                                "framework": "Rack/Rails",
                                "type": "config.ru",
                            }
                        )

                    if len(apps) >= 20:
                        break

            except Exception as e:  # pylint: disable=broad-exception-caught
                # reason: best-effort app-framework detection scan; a guest fs read error on
                # one path/file must not abort detection of other frameworks
                self.logger.debug(f"Failed to search {search_path}: {e}")

        return apps

    def _analyze_gemfile(self, gemfile: str) -> dict[str, Any] | None:
        """Analyze Ruby Gemfile."""
        try:
            content = self.file_ops.cat(gemfile)

            # Detect Rails
            framework = None
            if "rails" in content.lower():
                framework = "Ruby on Rails"
            elif "sinatra" in content.lower():
                framework = "Sinatra"

            return {
                "path": str(Path(gemfile).parent),
                "framework": framework or "Ruby (Bundler)",
                "type": "Gemfile",
            }
        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort app-framework detection scan; a guest fs read error on
            # one path/file must not abort detection of other frameworks
            return None

    def _detect_go_apps(self) -> list[dict[str, Any]]:
        """Detect Go applications."""
        apps = []

        search_paths = ["/opt", "/usr/local", "/home"]

        for search_path in search_paths:
            if not self.file_ops.is_dir(search_path):
                continue

            try:
                files = self.file_ops.find(search_path)
                for file in files[:200]:
                    if file.endswith("go.mod"):
                        apps.append(
                            {
                                "path": str(Path(file).parent),
                                "framework": "Go",
                                "type": "go.mod",
                            }
                        )

                    if len(apps) >= 20:
                        break

            except Exception as e:  # pylint: disable=broad-exception-caught
                # reason: best-effort app-framework detection scan; a guest fs read error on
                # one path/file must not abort detection of other frameworks
                self.logger.debug(f"Failed to search {search_path}: {e}")

        return apps

    def _detect_dotnet_apps(self) -> list[dict[str, Any]]:
        """Detect .NET applications."""
        apps = []

        search_paths = ["/opt", "/var/www", "/usr/local"]

        for search_path in search_paths:
            if not self.file_ops.is_dir(search_path):
                continue

            try:
                files = self.file_ops.find(search_path)
                for file in files[:200]:
                    if file.endswith(".csproj"):
                        apps.append(
                            {
                                "path": str(Path(file).parent),
                                "framework": ".NET",
                                "type": "csproj",
                            }
                        )
                    elif file.endswith(".sln"):
                        apps.append(
                            {
                                "path": str(Path(file).parent),
                                "framework": ".NET Solution",
                                "type": "sln",
                            }
                        )

                    if len(apps) >= 20:
                        break

            except Exception as e:  # pylint: disable=broad-exception-caught
                # reason: best-effort app-framework detection scan; a guest fs read error on
                # one path/file must not abort detection of other frameworks
                self.logger.debug(f"Failed to search {search_path}: {e}")

        return apps

    def get_framework_summary(self, frameworks: dict[str, Any]) -> dict[str, Any]:
        """
        Get framework summary.

        Args:
            frameworks: Framework detection results

        Returns:
            Summary dictionary
        """
        return {
            "total_apps": frameworks.get("total_apps", 0),
            "python_apps": len(frameworks.get("python", [])),
            "nodejs_apps": len(frameworks.get("nodejs", [])),
            "java_apps": len(frameworks.get("java", [])),
            "php_apps": len(frameworks.get("php", [])),
            "ruby_apps": len(frameworks.get("ruby", [])),
            "go_apps": len(frameworks.get("go", [])),
            "dotnet_apps": len(frameworks.get("dotnet", [])),
        }

    def list_web_frameworks(self, frameworks: dict[str, Any]) -> list[str]:
        """
        List detected web frameworks.

        Args:
            frameworks: Framework detection results

        Returns:
            List of web framework names
        """
        web_frameworks = []

        for lang, apps in frameworks.items():
            if lang == "total_apps":
                continue

            for app in apps:
                framework = app.get("framework", "")
                if any(
                    keyword in framework.lower()
                    for keyword in [
                        "django",
                        "flask",
                        "express",
                        "react",
                        "vue",
                        "rails",
                        "laravel",
                        "symfony",
                        "asp.net",
                    ]
                ):
                    web_frameworks.append(framework)

        return list(set(web_frameworks))
