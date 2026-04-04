# Google Infrastructure

## 1 Starting a new project

Project ID: **Project ID: gostcontrolpanel**

## 2 APIs & Services

- Cloud Run Admin API
- Cloud SQL Admin API
- Secret Manager API
- Cloud Build API
- Datastream API
- Compute Engine API
- BigQuery API
- Google Sheets API
- Cloud Logging API
- Cloud Pub/Sub API
- Dataform API
- Identity and Access Management (IAM) API	
- Google Drive API
- IAM Service Account Credentials API
- Service Usage API
- BigQuery Storage API
- Service Networking API
- Network Connectivity API
- Cloud Dataplex API
- Artifact Registry API


## 3 Service Accounts

#### Backend Service Account

Principals:

- BigQuery Data Editor
- BigQuery Job User
- BigQuery User
- Cloud SQL Client
- Cloud SQL Instance User
- Secret Manager Secret Accessor

#### Cloud Build runner Service Account

Principals:

- Artifact Registry Writer
- Cloud Run Admin
- Compute Network User
- Logs Writer
- Service Account User


#### Legacy Cloud Build Service Account (default SA)

Principals to Add:

- Cloud Build Service Account
- Cloud Run Admin
- Compute Network User
- Service Account User


## 4 Create the Virtual Network (VPC)

Create VPC Network

- Name: gcp-vpc
- Subnets: Custom.
- Subnet name: gcp-vpc-subnet
- Region: europe-west1
- IPv4 range: 10.0.0.0/24 

Create

## 5 Create the Database Bridge (Private Services Access)

Private Services Access 
From the **Allocated IP ranges for services** tab.

Allocate IP Range.

- Name: gcp-vpc-ip-range
- Prefix length: Select 24.

Allocate.

From the  **Private connections to services** tab.

Create connection.

- Network: gcp-vpc
- Assigned allocation: gcp-vpc-ip-range

Connect.
    

## 6 Cloud SQL

- Cloud SQL edition: Enterprise
- Database version: PostgreSql 18
- Password: Set 30 characters password for user postgrel and save on Secret Manager. This is the emergency password for access to the db.
- Instance ID: gost-db
- Enable password policies: True
- Set minimum length: 30
- Require complexity: True
- Disallow username in password: True

- Choose region and zonal availability: single zone - europe-west1
- Machine configuration: General purpose – Dedicated core - 2vCPU, 8GB
- Storage: 10 GB
- Enable automatic storage increases: True
- Connections: Private IP
- VPC network: gcp-vpc
- Allocated IP range: Automatic
- Private Service Connect (PSC): True
- [...]
- Flags and parameters:
    - cloudsql.iam_authentication (on)
    - cloudsql.logical_decoding (on)

From the  **Users** tab.

- Add User Account.
- Select Cloud IAM
- Principal/Email: field, paste the exact email address of the Backend Service Account

Add

## 7 Create the Artifact Registry (The Docker Vault)

Artifact Registry

- Create Repository
- Name: gcp-repo
- Format: Docker
- Location type: europe-west1 

Create.

## 8 Connect GitHub and Create the Trigger

Cloud Build

From the  **Triggers** tab.

1. Backend Trigger

- Connect Repository: Connect GitHub and pick the repositories
- Create Trigger
- Name: deploy-gcp-backend-on-push
- Region: europe-west1
- Event: Push to a branch
- Source: Pick the right branch
- Configuration: Cloud Build configuration file (yaml or json)
- Location: /cloudbuild.yaml
- Service account: Build runner Service Account

Create

2. Frontend Trigger

- Create Trigger
- Name: deploy-gpc-frontend-on-push
- Region: europe-west1
- Event: Push to a branch
- Source: Pick the right branch
- Included files filter: pentest-frontend/**
- Configuration: Cloud Build configuration file (yaml or json)
- Location: pentest-frontend/cloudbuild-frontend.yaml
- Substitution variables: _VITE_API_URL -> https://domain.name
- Service account: Build runner Service Account

Create

## 9 Reserve a Global Static IP

VPC network

From the  **IP addresses** tab.

- RESERVE EXTERNAL STATIC IP ADDRESS 
- Name: gcp-ip
- Network Service Tier: Premium
- IP Version: IPv4
- Type: Global 

Reserve.

From **Cloudflare Dashboard** or any oher Domain provider

- Go to your domain's DNS > Records page.
- Add record Type A
- Name: subdomain - gcp
- IPv4 address: Paste the Global IP address you copied from GCP.
- Proxy status: Click the toggle to turn it Off (DNS only / Gray cloud).
- Add record Type A
- Name: subdomain - api
- IPv4 address: Paste the Global IP address you copied from GCP.
- Proxy status: Click the toggle to turn it Off (DNS only / Gray cloud).

Save

## 10 Load Balancer














