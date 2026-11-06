variable "expected_account_id" {
  description = "Dedicated personal AWS account ID; no credentials belong here."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "Expected account must be exactly twelve digits."
  }
}

variable "environment_name" {
  description = "FitLog-only resource prefix, at most 24 characters."
  type        = string
  nullable    = false
  validation {
    condition     = length(var.environment_name) <= 24 && can(regex("^fitlog-demo-[a-z0-9]+(-[a-z0-9]+)*$", var.environment_name))
    error_message = "Use fitlog-demo- plus a lowercase alphanumeric/hyphen suffix, at most 24 characters."
  }
}

variable "availability_zones" {
  description = "Two distinct standard availability zones in Tokyo."
  type        = list(string)
  nullable    = false
  validation {
    condition = length(var.availability_zones) == 2 && length(distinct(var.availability_zones)) == 2 && alltrue([
      for az in var.availability_zones : can(regex("^ap-northeast-1[a-z]$", az))
    ])
    error_message = "Supply exactly two distinct ap-northeast-1 availability zones."
  }
}

variable "origin_verify_secret" {
  description = "Private CloudFront-to-ALB verifier; protect state and saved plans containing this value."
  type        = string
  nullable    = false
  sensitive   = true
  validation {
    condition     = can(regex("^[0-9a-f]{64}$", var.origin_verify_secret))
    error_message = "Origin verifier must be exactly 64 lowercase hexadecimal characters."
  }
}

variable "enable_public_distribution" {
  description = "Keep disabled until the separately approved deployment and real-AWS checks are ready."
  type        = bool
  nullable    = false
  default     = false
}

variable "backend_image_digest" {
  description = "Immutable SHA256 digest of the production image in this environment's ECR."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^sha256:[0-9a-f]{64}$", var.backend_image_digest))
    error_message = "Supply a lowercase sha256 digest, never a repository URL or tag."
  }
}

variable "backend_source_revision" {
  description = "Full Git commit used to build the backend image; verify artifact correspondence before deployment."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.backend_source_revision))
    error_message = "Supply the forty-character lowercase Git commit of the image source."
  }
}

variable "postgres_engine_version" {
  description = "Exact PostgreSQL 17 minor version; verify Tokyo availability before real AWS operations."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^17\\.[0-9]+$", var.postgres_engine_version))
    error_message = "Supply an exact PostgreSQL 17 minor version, such as 17.6."
  }
}

variable "db_final_snapshot_identifier" {
  description = "Unused environment-specific final snapshot name; deletion remains separately approved."
  type        = string
  nullable    = false
  validation {
    condition = (
      startswith(var.db_final_snapshot_identifier, "${var.environment_name}-final-") &&
      length(var.db_final_snapshot_identifier) <= 255 &&
      can(regex("^[a-zA-Z][a-zA-Z0-9-]*[a-zA-Z0-9]$", var.db_final_snapshot_identifier)) &&
      !strcontains(var.db_final_snapshot_identifier, "--")
    )
    error_message = "Use the environment's -final- prefix, at most 255 letters/digits/hyphens, with no trailing or consecutive hyphens."
  }
}

variable "enable_backend_service" {
  description = "Start one task only after image, application secret and database initialization are prepared."
  type        = bool
  nullable    = false
  default     = false
}

variable "enable_proxy_trust" {
  description = "Explicit proxy trust opt-in; flags do not prove the real CloudFront/ALB/task boundary."
  type        = bool
  nullable    = false
  default     = false
}

variable "allow_database_teardown" {
  description = "Explicit, separately approved deletion-protection removal after stopping all tasks and disabling public access."
  type        = bool
  nullable    = false
  default     = false
  validation {
    condition     = !var.allow_database_teardown || (!var.enable_backend_service && !var.enable_public_distribution)
    error_message = "Disable the backend service and public distribution before removing database deletion protection."
  }
}
