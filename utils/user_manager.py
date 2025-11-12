import orjson
from pathlib import Path
from typing import Optional, Dict, Any
import contextlib


class UserDataManager:
    def __init__(self, data_dir: str = "data/user"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.current_id: Optional[str] = None
        self.current_data: Optional[Dict[str, Any]] = None

    def get_user_file_path(self, user_id: str) -> Path:
        """获取用户数据文件路径"""
        return self.data_dir / f"{user_id}.json"

    def load_user_data(self, user_id: str) -> Dict[str, Any]:
        """加载用户JSON数据"""
        file_path = self.get_user_file_path(user_id)

        if file_path.exists():
            try:
                with open(file_path, 'rb') as f:
                    return orjson.loads(f.read())
            except (orjson.JSONDecodeError, FileNotFoundError):
                return {}
        else:
            return {}

    def save_user_data(self, user_id: str, data: Dict[str, Any]):
        """保存用户JSON数据"""
        file_path = self.get_user_file_path(user_id)

        with open(file_path, 'wb') as f:
            f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))

    @contextlib.contextmanager
    def user_session(self, user_id: str):
        """
        用户会话上下文管理器
        使用示例：
        with user_manager.user_session("user123") as user_data:
            user_data["name"] = "张三"
            user_data["last_login"] = "2024-01-01"
        """
        try:
            # 触发事件：开始会话
            self.current_id = user_id
            self.current_data = self.load_user_data(user_id)

            # 将数据传递给调用者
            yield self.current_data

        finally:
            # 触发事件：结束会话，保存数据
            if self.current_id and self.current_data is not None:
                self.save_user_data(self.current_id, self.current_data)

            # 清理资源
            self.current_id = None
            self.current_data = None

    def update_user_field(self, user_id: str, **kwargs):
        """快速更新用户字段（简化操作）"""
        with self.user_session(user_id) as user_data:
            user_data.update(kwargs)

    def get_user_info(self, user_id: str, field: Optional[str] = None):
        """获取用户信息"""
        data = self.load_user_data(user_id)
        return data.get(field) if field else data

    def close(self):
        """关闭管理器（清理资源）"""
        # 如果有未保存的数据，进行保存
        if self.current_id and self.current_data is not None:
            self.save_user_data(self.current_id, self.current_data)

        self.current_id = None
        self.current_data = None

udm = UserDataManager()