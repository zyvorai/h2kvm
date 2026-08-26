{{/*
Expand the name of the chart.
*/}}
{{- define "hyper2kvm-worker.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "hyper2kvm-worker.fullname" -}}
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
{{- define "hyper2kvm-worker.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "hyper2kvm-worker.labels" -}}
helm.sh/chart: {{ include "hyper2kvm-worker.chart" . }}
{{ include "hyper2kvm-worker.selectorLabels" . }}
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
{{- define "hyper2kvm-worker.selectorLabels" -}}
app.kubernetes.io/name: {{ include "hyper2kvm-worker.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app: hyper2kvm-worker
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "hyper2kvm-worker.serviceAccountName" -}}
{{- if .Values.rbac.serviceAccount.create }}
{{- default (include "hyper2kvm-worker.fullname" .) .Values.rbac.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.rbac.serviceAccount.name }}
{{- end }}
{{- end }}
