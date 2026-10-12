# 公开版验收结果

当前：2026-10-12，`2.0.0-flexible-assays`。下面保留2026-10-10公开版验收历史；所有验收使用合成数据，不是实际生物学验证。

## 2026-10-12 适用性扩展

- 120项自动测试通过，包括此前安全回归及五种文件格式、任意列映射、中英表头、µM转换、单位冲突、384孔关联、零浓度保留、IC50/EC50/CC50语义、错误方向拒绝和场景一致的报告/解释。
- 原96孔CSV+protocol示例的HTTP上传、确认、分析及六类导出继续通过。
- 浏览器实际验证单文件XLSX激活EC50、任意表头映射、标准版Word中的EC50、JSON活力CC50、酶IC50、384孔及原96孔示例切换和刷新访问；未调用付费模型。
- 扩展仅使用原锁定依赖，没有新增解析依赖；依赖已知漏洞扫描仍为2026-10-10的25包快照，不将旧扫描冒充当日新扫描。
- 使用边界与示例见APPLICABILITY.md。没有泛化到所有体外实验或所有文件内容。

## 2026-10-10 历史验收

## 已完成

- Windows x64、Python 3.11，独立虚拟环境安装新的依赖；`pip check`通过。
- 当时102项自动测试通过：合成曲线、异常/缺孔、质控、工具往返、路由、密钥隔离、SSRF、上传资源限制、XML实体、脚本CSP换行和自制报告结构。
- 新进程HTTP闭环：合成CSV/XLSX上传、设计确认闸门、分析、六种导出、页眉表格、本地Drug4追问；未认证请求返回401。
- 浏览器实际文件选择、确认、分析、Word下载、通用页眉和刷新访问通过；无应用脚本或CSP错误。
- 合成示例生成IC50分别为3.2、7.5、18.0 nM；拟合恢复到0.03 nM容差内。Drug4平坦曲线不报告IC50。
- 待发布文件检查：不包含运行密钥目录、企业附件、母版、企业标识、原面试PPT、浏览器缓存或依赖环境。
- 从Git暂存清单复制到干净源码目录后，102项测试和新进程HTTP闭环再次通过，无原始工作区附件依赖。

## 依赖范围

`requirements-lock.txt`：18个运行依赖；`requirements-dev-lock.txt`：额外6个测试依赖；可选PDF依赖1个。`requirements-audit-lock.txt`展平全部25个依赖，以避免`--no-deps`扫描遗漏嵌套引用。

完整在线扫描结果在本机`.checks/dependency-audit.json`，该私有检查目录不提交。公开摘要见`docs/dependency-audit-summary.json`。在本次扫描覆盖的公开记录中未发现已知漏洞；不代表没有未知漏洞或永远没有新增记录。

## 未声称完成

- 云模型和付费搜索在公开版未重新做真实付费验收；测试使用模拟协议。
- GitHub Actions文件已准备，本机检查不代表远程CI已执行。
- macOS/Linux完整启动、任意复杂布局、动力学、统计显著性和多用户生产系统尚未实现；激活EC50已在2.0版实现。
- 合成数据的低噪声和高拟合度不能用于估计实际实验准确率。
- 依赖固定了版本，尚未对所有安装包实行哈希校验或构建可复现二进制环境。

可在仓库根目录复现：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev-lock.txt
.\.venv\Scripts\python.exe tools\generate_sample.py
.\.venv\Scripts\python.exe tools\generate_flexible_samples.py
.\.venv\Scripts\python.exe -B -m unittest discover -s pharma_agent/tests -p "test_*.py"
.\.venv\Scripts\python.exe -B tools\verify_http.py
```
