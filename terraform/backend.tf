# Supply an environment-specific protected absolute path during real-operation
# init. Offline CI/mock validation continues to use init -backend=false.
terraform {
  backend "local" {}
}
