{{- define "ibce-bots.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ibce-bots.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s" (include "ibce-bots.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "ibce-bots.labels" -}}
app.kubernetes.io/name: {{ include "ibce-bots.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "ibce-bots.secretName" -}}
{{- if .Values.existingSecret -}}
{{- .Values.existingSecret -}}
{{- else -}}
{{- printf "ibce-bots-params" -}}
{{- end -}}
{{- end -}}

{{- define "ibce-bots.configMapName" -}}
{{- printf "ibce-bots-constants" -}}
{{- end -}}

{{- define "ibce-bots.pvcName" -}}
{{- printf "ibce-bots-data" -}}
{{- end -}}
