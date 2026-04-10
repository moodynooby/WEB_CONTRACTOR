# MongoDB Atlas Charts Setup Guide

This guide walks you through setting up MongoDB Atlas Charts to visualize your lead generation pipeline, campaigns, and query performance.

## Prerequisites

- A MongoDB Atlas account (free tier available at [mongodb.com/atlas](https://www.mongodb.com/atlas))
- An existing Atlas cluster with your Web Contractor data
- Admin or Project Owner access to your Atlas project

## Step 1: Enable Atlas Charts

1. Log in to your [MongoDB Atlas Dashboard](https://cloud.mongodb.com)
2. Navigate to your project
3. In the left sidebar, click on **Charts**
4. If prompted, click **Enable Charts** to activate the feature for your cluster
5. Wait for Charts to be enabled (usually takes 1-2 minutes)

## Step 2: Create a Dashboard

1. Click **Create Dashboard**
2. Name it `Web Contractor Analytics`
3. Add an optional description: "Lead generation and outreach pipeline analytics"
4. Click **Create**

## Step 3: Create Charts

### Chart 1: Lead Pipeline Status

**Purpose:** Visualize leads by status (pending_audit, qualified, unqualified)

1. Click **Add Chart** → **Chart**
2. Select your database and the `leads` collection
3. Configure:
   - **Chart Type:** Donut Chart
   - **Group By:** `status` (field)
   - **Metric:** Count
4. Click **Save**
5. Title: "Lead Pipeline Status"

### Chart 2: Leads Over Time

**Purpose:** Track lead accumulation over time

1. Click **Add Chart** → **Chart**
2. Select the `leads` collection
3. Configure:
   - **Chart Type:** Line Chart
   - **X-Axis:** `created_at` (Date, grouped by day)
   - **Y-Axis:** Count
4. Click **Save**
5. Title: "Leads Collected Over Time"

### Chart 3: Bucket Performance

**Purpose:** Compare lead generation across different buckets

1. Click **Add Chart** → **Chart**
2. Select the `leads` collection
3. Configure:
   - **Chart Type:** Bar Chart
   - **Group By:** `bucket_id` (or use $lookup to join with `buckets` collection for names)
   - **Metric:** Count
   - **Sort:** Descending
4. Click **Save**
5. Title: "Leads by Bucket"

### Chart 4: Email Campaign Performance

**Purpose:** Track email send status and success rates

1. Click **Add Chart** → **Chart**
2. Select the `email_campaigns` collection
3. Configure:
   - **Chart Type:** Donut Chart
   - **Group By:** `status` (sent, needs_review, failed, approved)
   - **Metric:** Count
4. Click **Save**
5. Title: "Email Campaign Status"

### Chart 5: Query Performance

**Purpose:** Monitor which queries are performing well

1. Click **Add Chart** → **Chart**
2. Select the `query_performance` collection
3. Configure:
   - **Chart Type:** Table
   - **Columns:** `query_pattern`, `city`, `total_leads_found`, `consecutive_failures`, `last_executed_at`
   - **Sort:** `total_leads_found` descending
   - **Filter:** `is_active` = true
4. Click **Save**
5. Title: "Query Performance Metrics"

### Chart 6: Daily Email Limits by Bucket

**Purpose:** Track daily email sending against limits

1. Click **Add Chart** → **Chart**
2. Select the `buckets` collection
3. Configure:
   - **Chart Type:** Bar Chart
   - **X-Axis:** `name` (bucket name)
   - **Y-Axis:** `daily_email_count`
   - **Reference Line:** `daily_email_limit`
4. Click **Save**
5. Title: "Daily Email Usage by Bucket"

## Step 4: Share Your Dashboard

### Option A: Public Dashboard Link

1. Open your dashboard
2. Click **Share** in the top right
3. Toggle **Make dashboard public**
4. Copy the public URL
5. Add this URL to your `.env` file:

```bash
ATLAS_CHARTS_URL=https://charts.mongodb.com/dashboards/your-project/your-dashboard-id
```

### Option B: Embedded in Tkinter GUI

The Tkinter GUI will open the Atlas Charts URL in your default browser when you click "View Analytics (Atlas)".

To customize the URL:

1. Copy your dashboard URL from Atlas
2. Add to your `.env` file:

```bash
ATLAS_CHARTS_URL=https://charts.mongodb.com/dashboards/your-project-id/your-dashboard-id
```

## Step 5: Set Up Auto-Refresh (Optional)

1. Open your dashboard
2. Click the **⚙️ Settings** icon
3. Set **Auto-refresh interval** to 5 minutes
4. This ensures your charts stay up-to-date without manual refresh

## Troubleshooting

### Charts Not Loading

- Ensure your Atlas cluster is running
- Verify the chart data source permissions allow read access
- Check that your IP is whitelisted in Atlas Network Access

### No Data Showing

- Run a discovery or pipeline task first to populate the database
- Verify the collection names match your database schema
- Check that documents have the expected fields

### Permission Errors

- Ensure your Atlas user has `read` access to the database
- For Chart sharing, you may need `Project Owner` or `Project Data Access Admin` role

## Additional Resources

- [MongoDB Charts Documentation](https://www.mongodb.com/docs/charts/)
- [Atlas Charts Quick Start](https://www.mongodb.com/docs/charts/quick-start/)
- [Chart Types Reference](https://www.mongodb.com/docs/charts/chart-types/)
