# 变更日志

本项目的所有重要变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [1.1.2] - 2026-02-28

### 修复
- **数据库游标资源泄漏修复**
  - 修复 `commands/reset.py` 中 `limit_reset` 方法的游标泄漏问题
  - 修复 `commands/blacklist.py` 中 `blacklist_add` 和 `blacklist_remove` 方法的游标泄漏问题
  - 修复 `commands/whitelist.py` 中 `whitelist_add` 和 `whitelist_remove` 方法的游标泄漏问题
  - 修复 `commands/group.py` 中 `limit_group` 方法的游标泄漏问题
  - 修复 `commands/user.py` 中 `limit_user` 方法的游标泄漏问题

### 优化
- **数据库初始化性能优化**
  - 将 `database/models.py` 中的 13 个独立 DDL 语句合并为一次 `executescript` 调用
  - 减少数据库初始化的网络请求次数，提升初始化性能
  - 代码更简洁易维护

### 改进
- **代码质量提升**
  - 所有数据库操作统一使用 `async with` 上下文管理器，确保游标资源正确释放
  - 符合 Python asyncio 资源管理最佳实践
  - 提高高并发场景下的稳定性，避免游标资源堆积

---

## [1.1.1] - 2026-02-28

### 修复
- **类型注解规范化**
  - 为 `main.py` 中所有命令函数的 `event` 参数添加 `AstrMessageEvent` 类型注解
  - 统一代码风格，与 `commands` 模块中的类型注解保持一致
  - 提升代码可读性和 IDE 静态检查支持

- **LLM 请求拦截器修复**
  - 修复错误的装饰器：将 `@filter.on_waiting_llm_request` 改为 `@filter.on_llm_request`
  - 修复方法签名：添加必需的第三个参数 `req: ProviderRequest`
  - 同步更新 `handlers/interceptors.py` 中的方法签名以匹配框架规范
  - 根据 AstrBot 框架文档，`@filter.on_llm_request` 必须接受三个参数 `(self, event, req)`

### 优化
- **代码质量提升**
  - 通过 ruff 代码质量检查，无错误或警告
  - 符合 PEP 8 编码规范
  - 改进文档注释，说明参数用途

---

## [1.1.0] - 2026-02-28

### 重构
- **命令处理器层 (commands 模块)**
  - 新增 `commands` 模块，实现完整的命令处理器架构
  - 所有管理功能独立为专门的命令处理器，提升代码可维护性
  
- **黑名单管理 (commands/blacklist.py)**
  - 支持添加用户到黑名单：`/limit blacklist add <用户ID>`
  - 支持从黑名单移除用户：`/limit blacklist remove <用户ID>`
  - 支持查看黑名单列表：`/limit blacklist list`
  - 黑名单用户将被阻止使用 AI 功能，优先级高于其他配置
  
- **白名单管理 (commands/whitelist.py)**
  - 支持添加用户到白名单：`/limit whitelist add <用户ID>`
  - 支持从白名单移除用户：`/limit whitelist remove <用户ID>`
  - 支持查看白名单列表：`/limit whitelist list`
  - 白名单用户可无限制使用 AI，不受计数限制
  
- **群组配置管理 (commands/group.py)**
  - 支持设置群组每日限制：`/limit group <次数>`
  - 支持设置群组计数模式：`/limit group mode <individual|shared>`
  - 私聊场景自动使用独立模式
  - 群聊场景可根据配置选择独立模式或共享模式
  
- **全局配置管理 (commands/global_config.py)**
  - 支持设置全局每日限制：`/limit global <次数>`
  - 支持设置全局计数模式：`/limit global mode <individual|shared>`
  - 全局配置适用于所有未单独配置的用户/群组
  
- **查询功能 (commands/query.py)**
  - 支持用户查询当前使用情况：`/limit`
  - 支持查看已使用次数和剩余次数
  - 支持查看当前生效的配置信息
  - 支持查看黑白名单状态
  
- **重置功能 (commands/reset.py)**
  - 支持管理员重置用户使用统计：`/limit reset user <用户ID>`
  - 支持管理员重置群组使用统计：`/limit reset group <群组ID>`
  - 支持管理员重置所有用户统计：`/limit reset all`
  - 重置操作需要管理员权限
  
- **统计功能 (commands/stats.py)**
  - 支持查看使用统计信息：`/limit stats`
  - 支持查看用户使用排行
  - 支持查看群组使用排行
  - 支持查看总计使用次数
  
- **用户管理 (commands/user.py)**
  - 支持查看用户详细信息：`/limit user <用户ID>`
  - 支持查看用户配置、使用记录、黑白名单状态
  - 支持设置用户专属配置：`/limit user <用户ID> <次数>`
  - 用户配置优先级高于群组和全局配置

### 优化
- **代码架构优化**
  - 引入命令处理器层，实现职责分离
  - 每个功能模块独立为单独的命令处理器
  - 提升代码可维护性和可扩展性
  - 便于后续添加新的命令功能

- **权限管理增强**
  - 统一的权限验证机制
  - 所有管理命令需要管理员权限
  - 完善的权限错误提示

- **代码组织优化**
  - `commands/` 目录存放所有命令处理器
  - 每个命令处理器职责单一，易于测试
  - 清晰的模块划分和依赖关系

---

## 版本说明

版本号格式：`主版本号.次版本号.修订号`

- **主版本号**：不兼容的 API 修改
- **次版本号**：向下兼容的功能性新增
- **修订号**：向下兼容的问题修正

---

## [1.0.2] - 2026-02-28

### 重构
- **核心逻辑优化**
  - 使用 `StarTools.get_data_dir` 获取规范的持久化目录
  - 优化数据库连接管理，实现连接复用与安全关闭
  - 移除 `register` 装饰器，改用 Star 基类标准注册方式
  - 优化数据库初始化逻辑，提升并发性能与代码可读性

### 文档
- 简化 README 版本历史，将详细变更日志移至 CHANGELOG.md

---

## [1.0.1] - 2026-02-28

### 移除
- **未实现的自动清理配置**
  - 从配置文件中移除 `cleanup_days` 配置项
  - 该功能在配置文件中定义但未实现代码，为避免混淆予以移除

---

## [1.0.0] - 2025-02-28

### 新增
- 🎉 **初始版本发布**
- ✨ **多级配置系统**
  - 全局默认配置（影响所有未单独配置的用户/群组）
  - 群组级别配置（支持独立模式和共享模式）
  - 用户级别配置（用户专属配置，优先级最高）
  - 配置优先级：黑名单 > 白名单 > 用户配置 > 群组配置 > 全局配置
  
- ✨ **黑白名单机制**
  - 黑名单功能：阻止指定用户使用 AI 功能
  - 白名单功能：允许指定用户无限制使用 AI
  - 支持添加/移除/查看黑名单和白名单
  - 黑名单优先级高于白名单
  
- ✨ **灵活的计数模式**
  - **独立模式** (individual)：每个用户独立计数，互不影响
  - **共享模式** (shared)：群组内所有用户共用计数
  - 私聊场景自动使用独立模式
  - 群聊场景可根据配置选择模式
  
- ✨ **高并发支持**
  - 使用 SQLite 数据库 + WAL 模式
  - 异步数据库操作，不阻塞 AI 请求
  - 原子性计数操作，保证数据准确性（UPSERT）
  - 针对查询场景优化的数据库索引
  
- ✨ **完整的指令系统**
  - `/limit` - 查询个人/群组使用情况
  - `/limit global` - 设置全局配置
  - `/limit group` - 设置群组配置
  - `/limit user` - 设置用户配置
  - `/limit blacklist add/remove/list` - 黑名单管理
  - `/limit whitelist add/remove/list` - 白名单管理
  - `/limit reset` - 重置指定用户/群组的使用计数
  - `/limit stats` - 查看使用统计信息
  
- ✨ **跨平台支持**
  - 支持 AIocQHttp、QQ 官方、Telegram、企业微信、飞书、钉钉
  - 支持 Discord、Slack、KOOK、VoceChat
  - 支持微信公众号、Satori、MissKey、LINE
  - 配置按平台隔离，互不影响
  
- ✨ **数据持久化**
  - 自动创建数据库和初始化表结构
  - 每日使用次数记录，支持历史查询
  - 配置数据持久化存储
  - 数据文件位于 `data/astrbot_plugin_limit_chan.db`

### 技术特性
- 📦 **异步架构**：全异步处理，不阻塞主流程
- 🔒 **线程安全**：使用异步锁保护初始化过程
- 💾 **数据完整性**：使用 UNIQUE 约束和 UPSERT 保证计数准确
- 🚀 **性能优化**：WAL 模式 + 索引优化，支持高并发场景
- 🛡️ **权限控制**：所有管理指令需要管理员权限
- 📊 **统计功能**：支持查询用户/群组使用历史

### 数据库结构
- `global_config` - 全局配置表
- `group_config` - 群组配置表
- `user_config` - 用户配置表
- `blacklist` - 黑名单表
- `whitelist` - 白名单表
- `ai_usage` - AI 使用记录表

### 适用场景
- 🏢 **群聊管理**：控制群组整体 AI 使用量
- 👥 **资源控制**：防止单个用户过度使用
- 🛡️ **防滥用**：通过黑白名单管理异常用户
- 📊 **配额管理**：为不同用户/群组分配不同配额
