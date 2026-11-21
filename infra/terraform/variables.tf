variable "region" {
  description = "AWS region for every CineBook resource"
  type        = string
  default     = "ap-south-1"
}

variable "ses_sender_email" {
  description = "SES-verified address the booking worker sends confirmations from"
  type        = string
  default     = "you@example.com"
}

variable "image_tag" {
  description = "Docker image tag (in ECR) the API servers run (1.1 = Phase 2: demo SMS; 1.2 = Phase 3: chat assistant)"
  type        = string
  default     = "1.2"
}

variable "running" {
  description = "true = everything on; false = paused (no load balancer, NAT stopped, 0 API servers, worker trigger off). Set in running.auto.tfvars by the pause/resume scripts."
  type        = bool
  default     = true
}

# ---------------------------------------------------------------- Phase 2: demo SMS
variable "sms_demo_numbers" {
  description = "Phone numbers allowed to receive demo SMS, e.g. +919812345678. Set in demo.auto.tfvars (git-ignored), never in code."
  type        = list(string)

  validation {
    condition     = length(var.sms_demo_numbers) > 0 && alltrue([for n in var.sms_demo_numbers : can(regex("^\\+[1-9][0-9]{7,14}$", n))])
    error_message = "Give at least one number in international form, for example +919812345678."
  }
}

variable "public_site_url" {
  description = "Website address used at the start of SMS chat links (no trailing slash). Change to the CloudFront address once it exists."
  type        = string
  default     = "http://localhost:5173"

  validation {
    condition     = can(regex("^https?://[^/]+$", var.public_site_url))
    error_message = "Use only the address, for example https://d1234abcd.cloudfront.net (no path, no trailing slash)."
  }
}

# ---------------------------------------------------------------- Phase 3: chat assistant
variable "chat_provider" {
  description = "Model service the chat assistant calls: gemini or bedrock"
  type        = string
  default     = "gemini"

  validation {
    condition     = contains(["gemini", "bedrock"], var.chat_provider)
    error_message = "Use gemini or bedrock."
  }
}

variable "chat_model_id" {
  description = "Model the chat assistant uses (the one chosen by infra/scripts/check-gemini.py)"
  type        = string
  default     = "gemini-3.5-flash-lite"
}
