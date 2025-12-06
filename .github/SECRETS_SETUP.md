# GitHub Actions Secrets Setup Guide

This document outlines the required secrets for the GitHub Actions workflows.

## Required Secrets

### Snyk Security Scan

1. **SNYK_TOKEN** (Required for Snyk workflows)
   - Get your Snyk API token from: https://app.snyk.io/account
   - Go to Settings → API Token
   - Copy the token and add it to GitHub Secrets:
     - Repository Settings → Secrets and variables → Actions → New repository secret
     - Name: `SNYK_TOKEN`
     - Value: Your Snyk API token

### SonarQube Analysis

1. **SONAR_TOKEN** (Required for SonarQube workflow)
   - Generate a token from your SonarQube server
   - Go to User → My Account → Security → Generate Token
   - Add to GitHub Secrets as `SONAR_TOKEN`

2. **SONAR_HOST_URL** (Required for SonarQube workflow)
   - Your SonarQube server URL (e.g., `https://sonarcloud.io` or your self-hosted URL)
   - Add to GitHub Secrets as `SONAR_HOST_URL`

## Optional Secrets

### Codecov (for test coverage)

If you want to use Codecov for coverage reporting:
1. Sign up at https://codecov.io
2. Add your repository
3. Copy the upload token (if required)
4. Add to GitHub Secrets as `CODECOV_TOKEN` (if needed)

## Setting Up Secrets

1. Go to your GitHub repository
2. Navigate to: **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add each secret with the name and value as specified above

## Workflow Status

- **Test**: Runs automatically, no secrets required
- **Lint**: Runs automatically, no secrets required
- **Format Check**: Runs automatically, no secrets required
- **Container Scan (Trivy)**: Runs automatically, no secrets required
- **Snyk Scan**: Requires `SNYK_TOKEN` secret
- **SonarQube**: Requires `SONAR_TOKEN` and `SONAR_HOST_URL` secrets

Note: Workflows that require secrets will be skipped or show warnings if secrets are not configured, but they won't fail the entire CI pipeline.


