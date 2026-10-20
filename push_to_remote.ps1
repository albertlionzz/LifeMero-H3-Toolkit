# push_to_remote.ps1
# LifeMero-H3-Toolkit 一键推送脚本（Windows）
# 用法：.\push_to_remote.ps1 -RemoteUrl <你的仓库URL>
param(
    [Parameter(Mandatory=$true)]
    [string]$RemoteUrl,
    [string]$Branch = "master"
)

$ErrorActionPreference = "Stop"
Write-Host "==> LifeMero-H3-Toolkit 推送到远程" -ForegroundColor Cyan
Write-Host "    远程: $RemoteUrl"
Write-Host "    分支: $Branch"

# 检查 git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "未检测到 git，正在用 winget 安装..." -ForegroundColor Yellow
    winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
}

git status --short > $null 2>&1
if ($LASTEXITCODE -ne 0) { Write-Host "请在仓库目录内运行本脚本" -ForegroundColor Red; exit 1 }

# 设置远程
$existing = git remote 2>$null
if ($existing -contains "origin") {
    git remote set-url origin $RemoteUrl
    Write-Host "==> 已更新 origin"
} else {
    git remote add origin $RemoteUrl
    Write-Host "==> 已添加 origin"
}

# 提交本地改动（如有）
git add .
if (git diff --cached --quiet) {
    Write-Host "==> 无新改动需要提交"
} else {
    git commit -m "update: $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
}

# 推送（首次 -u 建立跟踪）
git push -u origin $Branch
if ($LASTEXITCODE -eq 0) {
    Write-Host "==> 推送成功 ✓  仓库地址: $RemoteUrl" -ForegroundColor Green
} else {
    Write-Host "==> 推送失败。常见原因：" -ForegroundColor Red
    Write-Host "    1. 远程仓库不是空仓库（请勿勾选初始化README）"
    Write-Host "    2. 认证失败：GitHub 已不支持密码，需用 Personal Access Token 或 Git Credential Manager 登录"
    Write-Host "    3. 网络问题：GitHub 可能需要代理"
}
