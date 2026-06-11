# Git 自动推送方案

## 初始化仓库

```bash
git init -b main
git add .
git commit -m "feat: initial qq agent"
```

## 创建 GitHub 仓库并推送

```bash
gh repo create stillness990/agent-qq --public --source . --remote origin --push
```

如果远程仓库已存在：

```bash
git remote add origin https://github.com/stillness990/agent-qq.git
git push -u origin main
```

## 后续自动推送

可以复用博客项目中的自动同步思路：

```bash
git add .
git commit -m "chore: update agent-qq"
git push
```

生产环境建议不要完全无确认自动推送高风险代码，至少保留测试通过后再推送的步骤。

## 本次交付要求

项目完成后执行：

```bash
git add .
git commit -m "feat: initial qq agent"
git push
```

并输出：

- 提交内容
- Commit Hash
- 当前分支
- 推送结果
