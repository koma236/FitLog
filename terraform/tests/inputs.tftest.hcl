mock_provider "aws" {
  override_during = plan
}

variables {
  expected_account_id = "123456789012"
  environment_name    = "fitlog-demo-test"
  availability_zones  = ["ap-northeast-1a", "ap-northeast-1c"]
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
