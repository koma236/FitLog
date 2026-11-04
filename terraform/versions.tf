terraform {
  required_version = "= 1.15.1"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.71.0"
    }
  }
}

provider "aws" {
  region              = "ap-northeast-1"
  allowed_account_ids = [var.expected_account_id]
  default_tags {
    tags = {
      Project     = "FitLog"
      Environment = var.environment_name
      ManagedBy   = "Terraform"
    }
  }
}
