resource "aws_iam_role" "ecs" {
  for_each = toset(["task", "execution"])
  name     = "${var.environment_name}-${each.key}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = ["sts:AssumeRole"]
      Condition = {
        StringEquals = { "aws:SourceAccount" = var.expected_account_id }
        # ECS does not support restricting this condition to a specific cluster.
        ArnLike = { "aws:SourceArn" = "arn:aws:ecs:ap-northeast-1:${var.expected_account_id}:*" }
      }
    }]
  })
}

resource "aws_iam_role_policy" "media" {
  name = "image-storage"
  role = aws_iam_role.ecs["task"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ImageObjects"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = ["${aws_s3_bucket.private["media"].arn}/images/*"]
      },
      {
        Sid       = "ListImages"
        Effect    = "Allow"
        Action    = ["s3:ListBucket"]
        Resource  = [aws_s3_bucket.private["media"].arn]
        Condition = { StringEquals = { "s3:prefix" = "images/" } }
      }
    ]
  })
}

resource "aws_iam_role_policy" "execution" {
  name = "backend-startup"
  role = aws_iam_role.ecs["execution"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "RegistryToken"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = ["*"]
      },
      {
        Sid      = "BackendImage"
        Effect   = "Allow"
        Action   = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"]
        Resource = [aws_ecr_repository.backend.arn]
      },
      {
        Sid      = "BackendLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = ["${aws_cloudwatch_log_group.backend.arn}:*"]
      }
    ]
  })
}
