# 发布到GitHub

上传目标是本文件所在的 `AssayPilot-GitHub` 目录。不要选择外层工作区；外层材料不属于公开版。

2.0版发布包位于本目录的`dist/AssayPilot-2.0.0-flexible-assays.zip`；旧的1.9版ZIP不包含此次适用性扩展。压缩包只包含公开源码、合成数据和文档，不包含运行环境、密钥和检查缓存。

本地应先完成：数据生成、依赖安装、单元测试、HTTP闭环、浏览器检查、锁定依赖和泄漏检查。验收范围见VALIDATION.md。

## GitHub网页上传

创建新仓库，名称例如 `AssayPilot`。公开版已经使用合成数据和自制报告，但仍需人工查看待上传清单。上传根目录源码、`data`、`docs`、`tools`、`.github`和根目录说明/依赖/许可证文件。不要上传 `.venv`、`.checks`、`.local`或整个外层工作区。

## Git命令上传

本地仓库初始化后，在此目录运行；把网址替换成你本人仓库地址：

```powershell
git status --short
git add .
git diff --cached --stat
git commit -m "Prepare public synthetic demo"
git remote add origin https://github.com/YOUR_ACCOUNT/AssayPilot.git
git push -u origin main
```

如Git提示没有身份，用本人的名称和GitHub邮箱配置此仓库。无需把GitHub登录令牌写进源码；使用Git凭据管理器或GitHub官方认证入口。`.gitignore`不移除已经提交到历史的资料；若Key误上传，先撤销或轮换。

公开仓库页面可开启适用的秘密扫描/推送保护、Dependabot和私下漏洞报告。功能可用性取决于账号和仓库类型。上传后查看Actions，CI本地准备完成不等同于远程CI已经成功。

这只是源码仓库，GitHub Pages不能运行本项目Python后端。下载者在本机启动；部署服务需要另行设计托管、认证和数据策略。
