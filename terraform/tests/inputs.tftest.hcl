mock_provider "aws" {
  override_during = plan
  source          = "./tests/mocks"
}

variables {
  origin_verify_secret = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  expected_account_id  = "123456789012"
  environment_name     = "fitlog-demo-test"
  availability_zones   = ["ap-northeast-1a", "ap-northeast-1c"]
}

run "reject_short_account" {
  command = plan
  variables { expected_account_id = "123" }
  expect_failures = [var.expected_account_id]
}

run "reject_non_numeric_account" {
  command = plan
  variables { expected_account_id = "12345678901x" }
  expect_failures = [var.expected_account_id]
}

run "reject_other_project" {
  command = plan
  variables { environment_name = "other-demo-test" }
  expect_failures = [var.environment_name]
}

run "reject_empty_suffix" {
  command = plan
  variables { environment_name = "fitlog-demo-" }
  expect_failures = [var.environment_name]
}

run "reject_long_name" {
  command = plan
  variables { environment_name = "fitlog-demo-too-long-for-bucket-name" }
  expect_failures = [var.environment_name]
}

run "reject_duplicate_azs" {
  command = plan
  variables { availability_zones = ["ap-northeast-1a", "ap-northeast-1a"] }
  expect_failures = [var.availability_zones]
}

run "reject_single_az" {
  command = plan
  variables { availability_zones = ["ap-northeast-1a"] }
  expect_failures = [var.availability_zones]
}

run "reject_three_azs" {
  command = plan
  variables { availability_zones = ["ap-northeast-1a", "ap-northeast-1c", "ap-northeast-1d"] }
  expect_failures = [var.availability_zones]
}

run "reject_other_region" {
  command = plan
  variables { availability_zones = ["ap-northeast-1a", "us-east-1a"] }
  expect_failures = [var.availability_zones]
}

run "reject_empty_origin_secret" {
  command = plan
  variables { origin_verify_secret = "" }
  expect_failures = [var.origin_verify_secret]
}
run "reject_short_origin_secret" {
  command = plan
  variables { origin_verify_secret = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcde" }
  expect_failures = [var.origin_verify_secret]
}
run "reject_long_origin_secret" {
  command = plan
  variables { origin_verify_secret = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0" }
  expect_failures = [var.origin_verify_secret]
}
run "reject_uppercase_origin_secret" {
  command = plan
  variables { origin_verify_secret = "A123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" }
  expect_failures = [var.origin_verify_secret]
}
run "reject_wildcard_origin_secret" {
  command = plan
  variables { origin_verify_secret = "*123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" }
  expect_failures = [var.origin_verify_secret]
}
run "reject_question_mark_origin_secret" {
  command = plan
  variables { origin_verify_secret = "?123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" }
  expect_failures = [var.origin_verify_secret]
}
run "reject_whitespace_origin_secret" {
  command = plan
  variables { origin_verify_secret = " 123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" }
  expect_failures = [var.origin_verify_secret]
}
