resource "aws_s3_bucket" "private" {
  for_each      = toset(["static", "media"])
  bucket        = "${var.environment_name}-${each.key}-${var.expected_account_id}-ap-northeast-1"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "private" {
  for_each                = aws_s3_bucket.private
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "private" {
  for_each = aws_s3_bucket.private
  bucket   = each.value.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "private" {
  for_each = aws_s3_bucket.private
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_policy" "tls" {
  for_each = aws_s3_bucket.private
  bucket   = each.value.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = ["s3:*"]
      Resource  = [each.value.arn, "${each.value.arn}/*"]
      # AWS service-to-service context can redact transport attributes. This
      # exception grants no access; static OAC is granted separately below.
      Condition = { Bool = { "aws:SecureTransport" = "false", "aws:PrincipalIsAWSService" = "false" } }
      }], each.key == "static" ? [{
      Sid       = "CloudFrontStaticRead"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = ["s3:GetObject"]
      Resource  = ["${each.value.arn}/*"]
      Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.edge.arn } }
    }] : [])
  })
  depends_on = [aws_s3_bucket_public_access_block.private, aws_s3_bucket_ownership_controls.private]
}

resource "aws_ecr_repository" "backend" {
  name                 = "${var.environment_name}/backend"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/fitlog/${var.environment_name}/backend"
  retention_in_days = 7
}
