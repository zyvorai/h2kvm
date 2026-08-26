{{/*
Expand the name of the chart.
*/}}
{{- define "h2kvm-worker.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "h2kvm-worker.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "h2kvm-worker.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "h2kvm-worker.labels" -}}
helm.sh/chart: {{ include "h2kvm-worker.chart" . }}
{{ include "h2kvm-worker.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.labels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "h2kvm-worker.selectorLabels" -}}
app.kubernetes.io/name: {{ include "h2kvm-worker.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app: h2kvm-worker
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "h2kvm-worker.serviceAccountName" -}}
{{- if .Values.rbac.serviceAccount.create }}
{{- default (include "h2kvm-worker.fullname" .) .Values.rbac.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.rbac.serviceAccount.name }}
{{- end }}
{{- end }}
