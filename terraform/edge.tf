# Origin boundary: https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/restrict-access-to-load-balancer.html
data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_vpc_security_group_ingress_rule" "cloudfront" {
  security_group_id = aws_security_group.boundary["ingress"].id
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront.id
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_lb" "api" {
  name                       = "${var.environment_name}-api"
  load_balancer_type         = "application"
  internal                   = false
  ip_address_type            = "ipv4"
  subnets                    = [for subnet in aws_subnet.public : subnet.id]
  security_groups            = [aws_security_group.boundary["ingress"].id]
  preserve_host_header       = true
  drop_invalid_header_fields = true
  idle_timeout               = 65
}

resource "aws_lb_target_group" "api" {
  name        = "${var.environment_name}-api"
  vpc_id      = aws_vpc.foundation.id
  target_type = "ip"
  protocol    = "HTTP"
  port        = 8000
  health_check {
    enabled             = true
    protocol            = "HTTP"
    path                = "/api/health/live"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }
  # Targets are registered only by the follow-up ECS service, never here.
}

resource "aws_lb_listener" "api" {
  load_balancer_arn = aws_lb.api.arn
  protocol          = "HTTP"
  port              = 80
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      status_code  = "403"
      message_body = "Forbidden"
    }
  }
}

resource "aws_lb_listener_rule" "cloudfront" {
  listener_arn = aws_lb_listener.api.arn
  priority     = 1
  condition {
    http_header {
      http_header_name = "X-Fitlog-Origin-Verify"
      values           = [var.origin_verify_secret]
    }
  }
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_cloudfront_origin_access_control" "static" {
  name                              = "${var.environment_name}-static"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_function" "client_ip" {
  name    = "${var.environment_name}-client-ip"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = file("${path.module}/functions/client-ip.js")
}

resource "aws_cloudfront_cache_policy" "disabled" {
  name        = "${var.environment_name}-disabled"
  min_ttl     = 0
  default_ttl = 0
  max_ttl     = 0
  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_gzip   = false
    enable_accept_encoding_brotli = false
    headers_config { header_behavior = "none" }
    cookies_config { cookie_behavior = "none" }
    query_strings_config { query_string_behavior = "none" }
  }
}

resource "aws_cloudfront_origin_request_policy" "api" {
  name = "${var.environment_name}-api"
  # Host, Origin, Referer, CSRF and the Function's client IP must reach Django.
  headers_config { header_behavior = "allViewer" }
  cookies_config { cookie_behavior = "all" }
  query_strings_config { query_string_behavior = "all" }
}

resource "aws_cloudfront_distribution" "edge" {
  enabled             = var.enable_public_distribution
  is_ipv6_enabled     = true
  http_version        = "http2"
  default_root_object = "index.html"
  retain_on_delete    = false
  wait_for_deployment = true

  origin {
    origin_id                = "static"
    domain_name              = aws_s3_bucket.private["static"].bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.static.id
  }
  origin {
    origin_id   = "api"
    domain_name = aws_lb.api.dns_name
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
      origin_read_timeout    = 60
    }
    # AWS overwrites viewer-supplied values for these origin custom headers.
    custom_header {
      name  = "X-Fitlog-Origin-Verify"
      value = var.origin_verify_secret
    }
    custom_header {
      name  = "X-Fitlog-Forwarded-Proto"
      value = "https"
    }
  }

  default_cache_behavior {
    target_origin_id       = "static"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    viewer_protocol_policy = "https-only"
    compress               = false
    cache_policy_id        = aws_cloudfront_cache_policy.disabled.id
  }
  dynamic "ordered_cache_behavior" {
    for_each = ["/api", "/api/*"]
    content {
      path_pattern             = ordered_cache_behavior.value
      target_origin_id         = "api"
      allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
      cached_methods           = ["GET", "HEAD"]
      viewer_protocol_policy   = "https-only"
      compress                 = false
      cache_policy_id          = aws_cloudfront_cache_policy.disabled.id
      origin_request_policy_id = aws_cloudfront_origin_request_policy.api.id
      function_association {
        event_type   = "viewer-request"
        function_arn = aws_cloudfront_function.client_ip.arn
      }
    }
  }
  dynamic "custom_error_response" {
    for_each = toset([400, 403, 404, 405, 414, 416, 500, 501, 502, 503, 504])
    content {
      error_code            = custom_error_response.value
      error_caching_min_ttl = 0
      # Preserve original status and body; never rewrite API errors to index.html.
    }
  }
  viewer_certificate {
    cloudfront_default_certificate = true
  }
  restrictions {
    geo_restriction { restriction_type = "none" }
  }
  # Do not depend on the bucket policy: it depends on this distribution ARN.
}
