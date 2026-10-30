# XEK Studio (Phase 1-2 foundation)

Create cinema. Without limits. This version covers accounts and project saving. Later phases add screenplay, video, audio and export.

## Step 1: Put the code on GitHub
1. Go to github.com, click **New repository**, name it `xek-studio`, create it.
2. Click **uploading an existing file**, drag in ALL files from this folder (unzipped), and click **Commit changes**.

## Step 2: Create the database (free)
1. Go to supabase.com, create a free project.
2. Open **SQL Editor**, click **New query**, paste everything from `supabase/migrations/0001_projects.sql`, click **Run**.
3. Open **Project Settings > API**. Copy the **Project URL** and the **anon public key**.
4. Open **Authentication > URL Configuration**. Set **Site URL** to your Vercel address (from Step 3). Add `https://YOUR-ADDRESS/auth/callback` under Redirect URLs.

## Step 3: Put it online (free)
1. Go to vercel.com, sign in with GitHub, click **Add New > Project**, pick `xek-studio`.
2. Under **Environment Variables** add:
   - `NEXT_PUBLIC_SUPABASE_URL` = the Project URL
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` = the anon public key
3. Click **Deploy**. Wait about two minutes. Open the address Vercel gives you.

## Step 4: Check it works
Create an account, make a project, edit and save it, refresh the page (your data should still be there), delete it. If any step fails, send me the exact error text.

For quick testing without email confirmation: Supabase > Authentication > Providers > Email > turn off "Confirm email".
