import orjson
from pathlib import Path
from typing import Optional, Dict, Any, Literal
import contextlib

# 定义支持的数据类型
DataType = Literal["user", "guild"]


class UserDataManager:
    def __init__(self):
        self.base_data_dir: Optional[Path] = None
        self.current_id: Optional[str] = None
        self.current_data: Optional[Dict[str, Any]] = None
        self.current_type: Optional[DataType] = "user"

    def set_plugin_dir(self, data_dir: Path):
        """设置基础数据目录"""
        self.base_data_dir = data_dir / "data"
        self.base_data_dir.mkdir(parents=True, exist_ok=True)

    def get_data_dir(self, data_type: DataType = "user") -> Path:
        """获取指定类型的数据目录"""
        if self.base_data_dir is None:
            raise ValueError("请先调用 set_plugin_dir 设置基础数据目录")

        data_dir = self.base_data_dir / data_type
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    def get_user_file_path(self, user_id: str, data_type: DataType = "user") -> Path:
        """获取用户数据文件路径"""
        data_dir = self.get_data_dir(data_type)
        return data_dir / f"{user_id}.json"

    def load_user_data(self, user_id: str, data_type: DataType = "user") -> Dict[str, Any]:
        """加载用户JSON数据"""
        file_path = self.get_user_file_path(user_id, data_type)

        if file_path.exists():
            try:
                with open(file_path, 'rb') as f:
                    return orjson.loads(f.read())
            except (orjson.JSONDecodeError, FileNotFoundError):
                return {}
        else:
            return {}

    def save_user_data(self, user_id: str, data: Dict[str, Any], data_type: DataType = "user"):
        """保存用户JSON数据"""
        file_path = self.get_user_file_path(user_id, data_type)

        with open(file_path, 'wb') as f:
            f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))

    @contextlib.contextmanager
    def user_session(self, user_id: str, data_type: DataType = "user"):
        """
        用户会话上下文管理器

        使用示例：
        # 用户数据
        with user_manager.user_session("user123", "user") as user_data:
            user_data["name"] = "张三"
            user_data["last_login"] = "2024-01-01"

        # 频道数据
        with user_manager.user_session("guild123", "guild") as guild_data:
            guild_data["name"] = "测试频道"
            guild_data["member_count"] = 100
        """
        try:
            # 设置当前会话信息
            self.current_id = user_id
            self.current_type = data_type
            self.current_data = self.load_user_data(user_id, data_type)

            # 将数据传递给调用者
            yield self.current_data

        finally:
            # 触发事件：结束会话，保存数据
            if self.current_id and self.current_data is not None and self.current_type:
                self.save_user_data(self.current_id, self.current_data, self.current_type)

            # 清理资源
            self.current_id = None
            self.current_data = None
            self.current_type = None

    def update_user_field(self, user_id: str, data_type: DataType = "user", **kwargs):
        """快速更新用户字段（简化操作）"""
        with self.user_session(user_id, data_type) as user_data:
            user_data.update(kwargs)

    def get_user_info(self, user_id: str, field: Optional[str] = None, data_type: DataType = "user"):
        """获取用户信息"""
        data = self.load_user_data(user_id, data_type)
        return data.get(field) if field else data

    def delete_user_data(self, user_id: str, data_type: DataType = "user") -> bool:
        """删除用户数据文件"""
        file_path = self.get_user_file_path(user_id, data_type)
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def list_users(self, data_type: DataType = "user") -> list[str]:
        """列出指定类型的所有用户ID"""
        data_dir = self.get_data_dir(data_type)
        if not data_dir.exists():
            return []

        return [file.stem for file in data_dir.glob("*.json")]

    def close(self):
        """关闭管理器（清理资源）"""
        # 如果有未保存的数据，进行保存
        if self.current_id and self.current_data is not None and self.current_type:
            self.save_user_data(self.current_id, self.current_data, self.current_type)

        self.current_id = None
        self.current_data = None
        self.current_type = None


udm = UserDataManager()
