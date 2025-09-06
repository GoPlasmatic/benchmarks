# GitHub Secrets Setup Guide

To run the benchmarking workflow, you need to configure the following GitHub Secrets in your repository:

## Required Secrets

### 1. AZURE_CREDENTIALS
Azure Service Principal credentials in JSON format.

To create:
```bash
az ad sp create-for-rbac --name "github-benchmarks" \
  --role contributor \
  --scopes /subscriptions/{subscription-id} \
  --sdk-auth
```

This will output JSON like:
```json
{
  "clientId": "xxx",
  "clientSecret": "xxx",
  "subscriptionId": "xxx",
  "tenantId": "xxx"
}
```

Copy this entire JSON and save it as the `AZURE_CREDENTIALS` secret.

### 2. ACR_SERVER
Azure Container Registry server URL.

Example: `myregistry.azurecr.io`

### 3. ACR_USERNAME
Azure Container Registry username.

To get:
```bash
az acr credential show \
  --name myregistry \
  --query username -o tsv
```

### 4. ACR_PASSWORD
Azure Container Registry password.

To get:
```bash
az acr credential show \
  --name myregistry \
  --query passwords[0].value -o tsv
```

### 5. AZURE_STORAGE_KEY (Optional)
Storage account access key for uploading benchmark reports. If not provided, results will only be available as GitHub artifacts.

To get:
```bash
az storage account keys list \
  --account-name benchmarkstorage \
  --resource-group benchmarks-rg \
  --query '[0].value' -o tsv
```

## How to Add Secrets to GitHub

1. Go to your repository on GitHub
2. Click on **Settings** tab
3. Navigate to **Secrets and variables** → **Actions**
4. Click **New repository secret**
5. Add each secret with its name and value

## Verify Setup

After adding all secrets, you can verify the setup by:

1. Going to the **Actions** tab in your repository
2. Selecting **Benchmark Reframe Performance** workflow
3. Clicking **Run workflow**
4. Selecting test parameters
5. Monitoring the workflow execution

## Azure Resource Requirements

Ensure your Azure subscription has:
- Sufficient quota for VM sizes (Standard_B2s, Standard_D4s_v3, Standard_D8s_v3, Standard_D16s_v3)
- Container registry with Reframe image deployed
- (Optional) Storage account for report storage
- Network quota for VNets and public IPs

## Cost Considerations

Running the full benchmark suite (all VM sizes) will cost approximately:
- 2-core: ~$0.05/hour
- 4-core: ~$0.30/hour
- 8-core: ~$0.60/hour
- 16-core: ~$1.20/hour
- **Total per run: ~$2-3** (assuming 1-2 hours total runtime)

Resources are automatically cleaned up after each run to minimize costs.

## Troubleshooting

### Common Issues

1. **Docker pull fails**: Verify ACR_SERVER, ACR_USERNAME, and ACR_PASSWORD are correct
2. **VM provisioning fails**: Check Azure quota limits
3. **Storage upload fails**: Ensure AZURE_STORAGE_KEY is set (or remove storage upload step)
4. **Cleanup fails**: Manually delete resource groups if needed

### Manual Cleanup

If automatic cleanup fails, delete resource groups manually:
```bash
az group delete --name benchmarks-rg-2-core --yes
az group delete --name benchmarks-rg-4-core --yes
az group delete --name benchmarks-rg-8-core --yes
az group delete --name benchmarks-rg-16-core --yes
az group delete --name benchmarks-rg-benchmark --yes
```