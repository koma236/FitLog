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
