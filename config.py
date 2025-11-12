import os
import glob
from typing import Any, Dict, Optional
import orjson


class ConfigManager:
    def __init__(self):
        self._config_data: Dict[str, Any] = {}
        self._loaded = False

    def load_configs(self, config_dir: str = "data/config") -> None:
        """
        加载指定目录下的所有 JSON 配置文件

        Args:
            config_dir: 配置文件目录，默认为 "data/config"
        """
        if self._loaded:
            return

        if not os.path.exists(config_dir):
            raise FileNotFoundError(f"配置目录不存在: {config_dir}")

        # 查找所有 JSON 文件
        json_pattern = os.path.join(config_dir, "*.json")
        json_files = glob.glob(json_pattern)

        if not json_files:
            raise FileNotFoundError(f"在目录 {config_dir} 中未找到任何 JSON 文件")

        # 加载所有 JSON 文件
        for json_file in json_files:
            self._load_single_file(json_file)

        self._loaded = True
        print(f"成功加载 {len(json_files)} 个配置文件")

    def _load_single_file(self, file_path: str) -> None:
        """加载单个 JSON 文件"""
        try:
            with open(file_path, 'rb') as f:
                content = orjson.loads(f.read())

            # 验证文件格式
            if not isinstance(content, dict):
                raise ValueError(f"配置文件 {file_path} 的根元素必须是对象")

            # 将配置内容合并到总配置中
            for key, value in content.items():
                if key in self._config_data:
                    print(f"警告: 键 '{key}' 在多个配置文件中存在，将被覆盖")
                self._config_data[key] = value

        except orjson.JSONDecodeError as e:
            raise ValueError(f"配置文件 {file_path} JSON 格式错误: {e}")
        except Exception as e:
            raise RuntimeError(f"加载配置文件 {file_path} 时出错: {e}")

    def read(self, key: str) -> Any:
        """
        读取指定键的配置

        Args:
            key: 配置键名

        Returns:
            配置值，如果键不存在则返回 None
        """
        if not self._loaded:
            raise RuntimeError("配置未加载，请先调用 load_configs()")

        return self._config_data.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        """
        安全地读取配置，如果键不存在返回默认值

        Args:
            key: 配置键名
            default: 默认值

        Returns:
            配置值或默认值
        """
        if not self._loaded:
            raise RuntimeError("配置未加载，请先调用 load_configs()")

        return self._config_data.get(key, default)

    def get_nested(self, key_path: str, default: Any = None, separator: str = ".") -> Any:
        """
        读取嵌套配置，支持点分隔的路径

        Args:
            key_path: 配置路径，如 "database.host"
            default: 默认值
            separator: 路径分隔符

        Returns:
            配置值或默认值
        """
        if not self._loaded:
            raise RuntimeError("配置未加载，请先调用 load_configs()")

        keys = key_path.split(separator)
        current = self._config_data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default

        return current

    def list_keys(self) -> list:
        """返回所有可用的配置键"""
        return list(self._config_data.keys())

    def is_loaded(self) -> bool:
        """返回配置是否已加载"""
        return self._loaded


# 创建全局实例
_config_manager = ConfigManager()


# 公共接口函数
def config_load(config_dir: str = "data/config") -> None:
    """加载配置文件"""
    _config_manager.load_configs(config_dir)


def config_read(key: str) -> Any:
    """读取配置"""
    return _config_manager.read(key)


def config_get(key: str, default: Any = None) -> Any:
    """安全读取配置"""
    return _config_manager.get(key, default)


def config_get_nested(key_path: str, default: Any = None, separator: str = ".") -> Any:
    """读取嵌套配置"""
    return _config_manager.get_nested(key_path, default, separator)


def config_list_keys() -> list:
    """列出所有配置键"""
    return _config_manager.list_keys()
