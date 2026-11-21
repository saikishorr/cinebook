# Terraform and provider versions, and the AWS region.
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  # State is kept locally in terraform.tfstate (git-ignored; keep a backup).
}

provider "aws" {
  region = var.region
}
