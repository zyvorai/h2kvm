{{/*
Expand the name of the chart.
*/}}
{{- define "h2kvm-operator.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "h2kvm-operator.fullname" -}}
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
{{- define "h2kvm-operator.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "h2kvm-operator.labels" -}}
helm.sh/chart: {{ include "h2kvm-operator.chart" . }}
{{ include "h2kvm-operator.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "h2kvm-operator.selectorLabels" -}}
app.kubernetes.io/name: {{ include "h2kvm-operator.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Operator labels
*/}}
{{- define "h2kvm-operator.operatorLabels" -}}
{{ include "h2kvm-operator.labels" . }}
app.kubernetes.io/component: operator
{{- end }}

{{/*
Operator selector labels
*/}}
{{- define "h2kvm-operator.operatorSelectorLabels" -}}
{{ include "h2kvm-operator.selectorLabels" . }}
app.kubernetes.io/component: operator
{{- end }}

{{/*
Webhook labels
*/}}
{{- define "h2kvm-operator.webhookLabels" -}}
{{ include "h2kvm-operator.labels" . }}
app.kubernetes.io/component: webhook
{{- end }}

{{/*
Webhook selector labels
*/}}
{{- define "h2kvm-operator.webhookSelectorLabels" -}}
{{ include "h2kvm-operator.selectorLabels" . }}
app.kubernetes.io/component: webhook
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "h2kvm-operator.serviceAccountName" -}}
{{- if .Values.operator.serviceAccount.create }}
{{- default (include "h2kvm-operator.fullname" .) .Values.operator.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.operator.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Operator image
*/}}
{{- define "h2kvm-operator.operatorImage" -}}
{{- if .Values.operator.image.digest }}
{{- printf "%s@%s" .Values.operator.image.repository .Values.operator.image.digest }}
{{- else }}
{{- printf "%s:%s" .Values.operator.image.repository (.Values.operator.image.tag | default .Chart.AppVersion) }}
{{- end }}
{{- end }}

{{/*
Webhook image
*/}}
{{- define "h2kvm-operator.webhookImage" -}}
{{- if .Values.webhook.image.digest }}
{{- printf "%s@%s" .Values.webhook.image.repository .Values.webhook.image.digest }}
{{- else }}
{{- printf "%s:%s" .Values.webhook.image.repository (.Values.webhook.image.tag | default .Chart.AppVersion) }}
{{- end }}
{{- end }}

{{/*
Namespace
*/}}
{{- define "h2kvm-operator.namespace" -}}
{{- .Values.global.namespace | default .Release.Namespace }}
{{- end }}

{{/*
Webhook service name
*/}}
{{- define "h2kvm-operator.webhookServiceName" -}}
{{- printf "%s-webhook" (include "h2kvm-operator.fullname" .) }}
{{- end }}

{{/*
Webhook certificate secret name
*/}}
{{- define "h2kvm-operator.webhookCertSecretName" -}}
{{- if .Values.webhook.tls.existingSecret }}
{{- .Values.webhook.tls.existingSecret }}
{{- else }}
{{- printf "%s-webhook-certs" (include "h2kvm-operator.fullname" .) }}
{{- end }}
{{- end }}

{{/*
Webhook CA bundle (placeholder, will be patched by cert job or cert-manager)
*/}}
{{- define "h2kvm-operator.webhookCABundle" -}}
{{- print "Cg==" }}
{{- end }}

{{/*
Detect if running on OpenShift
*/}}
{{- define "h2kvm-operator.isOpenShift" -}}
{{- if .Values.openshift.enabled }}
{{- true }}
{{- else if and .Values.openshift.autoDetect (.Capabilities.APIVersions.Has "route.openshift.io/v1") }}
{{- true }}
{{- else }}
{{- false }}
{{- end }}
{{- end }}

{{/*
Platform name (kubernetes or openshift)
*/}}
{{- define "h2kvm-operator.platform" -}}
{{- if eq (include "h2kvm-operator.isOpenShift" .) "true" }}
{{- print "openshift" }}
{{- else }}
{{- print "kubernetes" }}
{{- end }}
{{- end }}

{{/*
Platform-specific annotations
*/}}
{{- define "h2kvm-operator.platformAnnotations" -}}
{{- if eq (include "h2kvm-operator.isOpenShift" .) "true" }}
{{- with .Values.openshift.templateMetadata.annotations }}
{{- toYaml . }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Platform-specific labels
*/}}
{{- define "h2kvm-operator.platformLabels" -}}
{{- if eq (include "h2kvm-operator.isOpenShift" .) "true" }}
{{- with .Values.openshift.templateMetadata.labels }}
{{- toYaml . }}
{{- end }}
{{- end }}
{{- end }}
