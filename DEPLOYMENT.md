# Permanent Team Link Deployment

You need a cloud host to get one stable URL that all team members can use.

## Recommended: Streamlit Community Cloud (Free)

### 1. Push this project to GitHub

Run these commands in this folder:

```powershell
git init
git add .
git commit -m "Initial Streamlit app"
```

Create an empty GitHub repository, then connect and push:

```powershell
git remote add origin https://github.com/<your-username>/<your-repo>.git
git branch -M main
git push -u origin main
```

### 2. Deploy on Streamlit Cloud

1. Open https://share.streamlit.io
2. Sign in with GitHub.
3. Click New app.
4. Select your repository and branch `main`.
5. Set Main file path to `app.py`.
6. Click Deploy.

### 3. Share the permanent URL

Streamlit will provide a URL like:

`https://<your-app-name>.streamlit.app`

This is the link you share with the team.

## Important Notes

- Unlike local tunnels, this link stays available even when your laptop is off.
- If you update code, push commits to GitHub and Streamlit can auto-redeploy.
- Keep secrets out of code; use Streamlit Secrets for credentials.
