{{/*
Expand the name of the chart.
*/}}
{{- define "hyper2kvm-operator.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "hyper2kvm-operator.fullname" -}}
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
{{- define "hyper2kvm-operator.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "hyper2kvm-operator.labels" -}}
helm.sh/chart: {{ include "hyper2kvm-operator.chart" . }}
{{ include "hyper2kvm-operator.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "hyper2kvm-operator.selectorLabels" -}}
app.kubernetes.io/name: {{ include "hyper2kvm-operator.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Operator labels
*/}}
{{- define "hyper2kvm-operator.operatorLabels" -}}
{{ include "hyper2kvm-operator.labels" . }}
app.kubernetes.io/component: operator
{{- end }}

{{/*
Operator selector labels
*/}}
{{- define "hyper2kvm-operator.operatorSelectorLabels" -}}
{{ include "hyper2kvm-operator.selectorLabels" . }}
app.kubernetes.io/component: operator
{{- end }}

{{/*
Webhook labels
*/}}
{{- define "hyper2kvm-operator.webhookLabels" -}}
{{ include "hyper2kvm-operator.labels" . }}
app.kubernetes.io/component: webhook
{{- end }}

{{/*
Webhook selector labels
*/}}
{{- define "hyper2kvm-operator.webhookSelectorLabels" -}}
{{ include "hyper2kvm-operator.selectorLabels" . }}
app.kubernetes.io/component: webhook
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "hyper2kvm-operator.serviceAccountName" -}}
{{- if .Values.operator.serviceAccount.create }}
{{- default (include "hyper2kvm-operator.fullname" .) .Values.operator.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.operator.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Operator image
*/}}
{{- define "hyper2kvm-operator.operatorImage" -}}
{{- if .Values.operator.image.digest }}
{{- printf "%s@%s" .Values.operator.image.repository .Values.operator.image.digest }}
{{- else }}
{{- printf "%s:%s" .Values.operator.image.repository (.Values.operator.image.tag | default .Chart.AppVersion) }}
{{- end }}
{{- end }}

{{/*
Webhook image
*/}}
{{- define "hyper2kvm-operator.webhookImage" -}}
{{- if .Values.webhook.image.digest }}
{{- printf "%s@%s" .Values.webhook.image.repository .Values.webhook.image.digest }}
{{- else }}
{{- printf "%s:%s" .Values.webhook.image.repository (.Values.webhook.image.tag | default .Chart.AppVersion) }}
{{- end }}
{{- end }}

{{/*
Namespace
*/}}
{{- define "hyper2kvm-operator.namespace" -}}
{{- .Values.global.namespace | default .Release.Namespace }}
{{- end }}

{{/*
Webhook service name
*/}}
{{- define "hyper2kvm-operator.webhookServiceName" -}}
{{- printf "%s-webhook" (include "hyper2kvm-operator.fullname" .) }}
{{- end }}

{{/*
Webhook certificate secret name
*/}}
{{- define "hyper2kvm-operator.webhookCertSecretName" -}}
{{- if .Values.webhook.tls.existingSecret }}
{{- .Values.webhook.tls.existingSecret }}
{{- else }}
{{- printf "%s-webhook-certs" (include "hyper2kvm-operator.fullname" .) }}
{{- end }}
{{- end }}

{{/*
Webhook CA bundle (placeholder, will be patched by cert job or cert-manager)
*/}}
{{- define "hyper2kvm-operator.webhookCABundle" -}}
{{- print "Cg==" }}
{{- end }}

{{/*
Detect if running on OpenShift
*/}}
{{- define "hyper2kvm-operator.isOpenShift" -}}
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
{{- define "hyper2kvm-operator.platform" -}}
{{- if eq (include "hyper2kvm-operator.isOpenShift" .) "true" }}
{{- print "openshift" }}
{{- else }}
{{- print "kubernetes" }}
{{- end }}
{{- end }}

{{/*
Platform-specific annotations
*/}}
{{- define "hyper2kvm-operator.platformAnnotations" -}}
{{- if eq (include "hyper2kvm-operator.isOpenShift" .) "true" }}
{{- with .Values.openshift.templateMetadata.annotations }}
{{- toYaml . }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Platform-specific labels
*/}}
{{- define "hyper2kvm-operator.platformLabels" -}}
{{- if eq (include "hyper2kvm-operator.isOpenShift" .) "true" }}
{{- with .Values.openshift.templateMetadata.labels }}
{{- toYaml . }}
{{- end }}
{{- end }}
{{- end }}
