# Values are provisioned separately. Never add a secret_version or value data source.
resource "aws_secretsmanager_secret" "application" {
  name                    = "${var.environment_name}/application"
  description             = "FitLog application keys and non-administrative DB password"
  recovery_window_in_days = 7
}

resource "aws_iam_role_policy" "application_secret" {
  name = "application-startup"
  role = aws_iam_role.ecs["execution"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "ApplicationStartup"
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [aws_secretsmanager_secret.application.arn]
    }]
  })
}
