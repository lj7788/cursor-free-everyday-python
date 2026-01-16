#!/usr/bin/env python3
import os
import sys
import json
import random
import string
import uuid
import datetime
import shutil
import subprocess
from pathlib import Path

# 尝试导入所需的库
try:
    import colorama
    from colorama import Fore, Style
    colorama.init()
except ImportError:
    print("请安装 colorama 库: pip install colorama")
    sys.exit(1)

try:
    import psutil
except ImportError:
    print("请安装 psutil 库: pip install psutil")
    sys.exit(1)

try:
    import appdirs
except ImportError:
    print("请安装 appdirs 库: pip install appdirs")
    sys.exit(1)

# 颜色定义
RED = Fore.RED
GREEN = Fore.GREEN
YELLOW = Fore.YELLOW
BLUE = Fore.BLUE
CYAN = Fore.CYAN
RESET = Style.RESET_ALL

# 最大重试次数和等待时间
MAX_RETRIES = 5
WAIT_TIME_SECONDS = 1

def get_storage_file_path():
    """获取配置文件路径"""
    config_dir = appdirs.user_config_dir()
    return Path(config_dir) / "Cursor" / "User" / "globalStorage" / "storage.json"

def get_backup_dir_path():
    """获取备份目录路径"""
    config_dir = appdirs.user_config_dir()
    return Path(config_dir) / "Cursor" / "User" / "globalStorage" / "backups"

def get_cursor_package_path():
    """获取 Cursor 包文件路径"""
    local_app_data = appdirs.user_data_dir()
    primary_path = Path(local_app_data) / "Programs" / "cursor" / "resources" / "app" / "package.json"
    if primary_path.exists():
        return primary_path
    alt_path = Path(local_app_data) / "cursor" / "resources" / "app" / "package.json"
    if alt_path.exists():
        return alt_path
    return None

def get_cursor_updater_path():
    """获取 Cursor 更新器路径"""
    local_app_data = appdirs.user_data_dir()
    return Path(local_app_data) / "cursor-updater"

def press_enter_to_exit(exit_code=0):
    """按回车键退出"""
    input("按 Enter 键退出...")
    sys.exit(exit_code)

def is_admin():
    """检查是否以管理员权限运行"""
    try:
        return os.geteuid() == 0
    except AttributeError:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0

def get_random_hex(length):
    """生成随机十六进制字符串"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def new_standard_machine_id():
    """生成新的标准机器 ID"""
    # 模板: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
    # y 是 8, 9, a, b 中的一个
    id_template = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx"
    result = []
    for char in id_template:
        if char == '-' or char == '4':
            result.append(char)
        elif char == 'x':
            result.append(random.choice('0123456789abcdef'))
        elif char == 'y':
            result.append(random.choice('89ab'))
    return ''.join(result)

def get_cursor_version():
    """获取 Cursor 版本"""
    package_path = get_cursor_package_path()
    if not package_path:
        print(f"{YELLOW}[WARNING] 无法确定 Cursor 的 package.json 路径{RESET}")
        return None
    if not package_path.exists():
        print(f"{YELLOW}[WARNING] package.json 未在 {package_path} 找到{RESET}")
        return None
    try:
        with open(package_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('version')
    except Exception as e:
        print(f"{RED}[ERROR] 读取 package.json 失败: {e}{RESET}")
        return None

def close_cursor_process(process_name):
    """关闭 Cursor 进程"""
    processes_to_kill = []
    for proc in psutil.process_iter(['pid', 'name', 'exe']):
        try:
            if proc.info['name'].lower() == process_name.lower():
                processes_to_kill.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    if processes_to_kill:
        print(f"{YELLOW}[WARNING] 发现运行中的 {process_name}{RESET}")
        for proc in processes_to_kill:
            print(f"  PID: {proc.info['pid']}, Name: {proc.info['name']}, Path: {proc.info['exe']}")
        
        print(f"{YELLOW}[WARNING] 尝试关闭 {process_name}...{RESET}")
        for proc in processes_to_kill:
            try:
                proc.terminate()
            except Exception as e:
                print(f"{RED}[ERROR] 无法向 {process_name} (PID: {proc.info['pid']}) 发送终止信号: {e}{RESET}")
        
        retry_count = 0
        while retry_count < MAX_RETRIES:
            still_running = []
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    if proc.info['name'].lower() == process_name.lower():
                        still_running.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            if not still_running:
                break
            
            retry_count += 1
            if retry_count >= MAX_RETRIES:
                print(f"{RED}[ERROR] 在 {MAX_RETRIES} 次尝试后无法关闭 {process_name}{RESET}")
                for proc in still_running:
                    print(f"  仍在运行 - PID: {proc.info['pid']}, Name: {proc.info['name']}, Path: {proc.info['exe']}")
                print(f"{RED}[ERROR] 请手动关闭进程并重试{RESET}")
                press_enter_to_exit(1)
            
            print(f"{YELLOW}[WARNING] 等待进程关闭，尝试 {retry_count}/{MAX_RETRIES}...{RESET}")
            import time
            time.sleep(WAIT_TIME_SECONDS)
        
        print(f"{GREEN}[INFO] {process_name} 成功关闭{RESET}")

def update_machine_guid(backup_dir):
    """更新注册表中的 MachineGuid"""
    if sys.platform != 'win32':
        print(f"{YELLOW}[INFO] 跳过 MachineGuid 更新（非 Windows 系统）{RESET}")
        return False
    
    print(f"{GREEN}[INFO] 更新注册表中的 MachineGuid...{RESET}")
    
    try:
        import winreg
        
        reg_path = r"SOFTWARE\Microsoft\Cryptography"
        reg_key_name = "MachineGuid"
        full_reg_key_path_for_export = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography"
        
        # 打开注册表键
        try:
            hklm = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
            crypto_key = winreg.OpenKey(hklm, reg_path, 0, winreg.KEY_READ | winreg.KEY_WRITE)
        except Exception as e:
            print(f"{RED}[ERROR] 无法打开注册表键 '{reg_path}': {e}。请确保您有管理员权限。{RESET}")
            return False
        
        # 获取当前值
        original_guid = ""
        try:
            original_guid = winreg.QueryValueEx(crypto_key, reg_key_name)[0]
            print(f"{GREEN}[INFO] 当前注册表值:{RESET}")
            print(f"  {full_reg_key_path_for_export}")
            print(f"    {reg_key_name}    REG_SZ    {original_guid}")
        except Exception as e:
            print(f"{RED}[ERROR] 无法获取当前 {reg_key_name}: {e}。这可能表示存在问题或该值不存在。{RESET}")
        
        # 确保备份目录存在
        if not backup_dir.exists():
            try:
                backup_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"{YELLOW}[WARNING] 无法创建注册表备份目录: {e}。继续操作但不备份注册表。{RESET}")
        
        # 备份注册表
        backup_file_name = f"MachineGuid_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.reg"
        backup_file_path = backup_dir / backup_file_name
        backup_command = f"reg.exe export \"{full_reg_key_path_for_export}\" \"{backup_file_path}\" /y"
        
        print(f"{GREEN}[INFO] 尝试将注册表键备份到: {backup_file_path}{RESET}")
        try:
            subprocess.run(backup_command, shell=True, check=True)
            print(f"{GREEN}[INFO] 注册表键成功备份。{RESET}")
        except Exception as e:
            print(f"{YELLOW}[WARNING] 注册表备份命令执行失败: {e}。继续操作但不备份注册表。{RESET}")
        
        # 设置新值
        new_guid = str(uuid.uuid4())
        try:
            winreg.SetValueEx(crypto_key, reg_key_name, 0, winreg.REG_SZ, new_guid)
            print(f"{GREEN}[INFO] 注册表值 {reg_key_name} 设置为: {new_guid}{RESET}")
            
            # 验证
            verify_guid = winreg.QueryValueEx(crypto_key, reg_key_name)[0]
            if verify_guid == new_guid:
                print(f"{GREEN}[INFO] 注册表更新验证成功。{RESET}")
                print(f"  {full_reg_key_path_for_export}")
                print(f"    {reg_key_name}    REG_SZ    {new_guid}")
                return True
            else:
                print(f"{RED}[ERROR] 注册表验证失败: 更新后的值 ({verify_guid}) 与预期值 ({new_guid}) 不匹配。{RESET}")
                return False
        except Exception as e:
            print(f"{RED}[ERROR] 无法设置注册表值 {reg_key_name}: {e}。{RESET}")
            
            # 尝试从备份恢复
            if original_guid and backup_file_path.exists():
                print(f"{YELLOW}[INFO] 尝试从备份恢复注册表: {backup_file_path}{RESET}")
                restore_command = f"reg.exe import \"{backup_file_path}\""
                try:
                    subprocess.run(restore_command, shell=True, check=True)
                    print(f"{GREEN}[INFO] 注册表已从备份成功恢复。{RESET}")
                except Exception as re:
                    print(f"{RED}[ERROR] 执行注册表恢复命令失败: {re}。需要从 {backup_file_path} 手动恢复{RESET}")
            return False
    except ImportError:
        print(f"{YELLOW}[INFO] 跳过 MachineGuid 更新（无法导入 winreg 模块）{RESET}")
        return False

def update_storage_file(storage_file_path, machine_id, mac_machine_id, dev_device_id, sqm_id):
    """更新配置文件"""
    if not storage_file_path.exists():
        print(f"{RED}[ERROR] 配置文件未找到: {storage_file_path}{RESET}")
        print(f"{YELLOW}[TIP] 请先安装并运行一次 Cursor 再使用此脚本{RESET}")
        return False
    
    try:
        with open(storage_file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
    except Exception as e:
        print(f"{RED}[ERROR] 读取配置文件失败 {storage_file_path}: {e}{RESET}")
        return False
    
    try:
        config = json.loads(original_content)
    except Exception as e:
        print(f"{RED}[ERROR] 解析配置文件 JSON 失败: {e}{RESET}")
        return False
    
    # 确保 telemetry 路径存在
    if 'telemetry' not in config or not isinstance(config['telemetry'], dict):
        if isinstance(config, dict):
            config['telemetry'] = {}
        else:
            print(f"{RED}[ERROR] 配置根不是 JSON 对象。无法设置 telemetry。{RESET}")
            return False
    
    # 更新特定值
    config['telemetry']['machineId'] = machine_id
    config['telemetry']['macMachineId'] = mac_machine_id
    config['telemetry']['devDeviceId'] = dev_device_id
    config['telemetry']['sqmId'] = sqm_id
    
    try:
        updated_json = json.dumps(config, indent=2, ensure_ascii=False)
        with open(storage_file_path, 'w', encoding='utf-8') as f:
            f.write(updated_json)
        print(f"{GREEN}[INFO] 配置文件在 {storage_file_path} 成功更新{RESET}")
        return True
    except Exception as e:
        print(f"{RED}[ERROR] 将更新后的配置写入 {storage_file_path} 失败: {e}{RESET}")
        # 尝试恢复原始内容
        try:
            with open(storage_file_path, 'w', encoding='utf-8') as f:
                f.write(original_content)
        except Exception as re:
            print(f"{RED}[ERROR] 严重: 在写入错误后无法将原始内容恢复到 {storage_file_path}。{RESET}")
        return False

def main():
    """主函数"""
    # 检查管理员权限
    if not is_admin():
        print(f"{RED}[ERROR] 请以管理员权限运行此脚本{RESET}")
        print("右键点击可执行文件并选择'以管理员身份运行'")
        press_enter_to_exit(1)
    
    # 清屏
    if sys.platform == 'win32':
        os.system('cls')
    else:
        os.system('clear')
    
    # 显示 Logo
    print(f"{Fore.CYAN}")
    print(r"""
    ██████╗██╗   ██╗██████╗ ███████╗ ██████╗ ██████╗ 
   ██╔════╝██║   ██║██╔══██╗██╔════╝██╔═══██╗██╔══██╗
   ██║     ██║   ██║██████╔╝███████╗██║   ██║██████╔╝
   ██║     ██║   ██║██╔══██╗╚════██║██║   ██║██╔══██╗
   ╚██████╗╚██████╔╝██║  ██║███████║╚██████╔╝██║  ██║
    ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝

""")
    print(f"{RESET}")
    print(f"{BLUE}================================{RESET}")
    print(f"   {GREEN}Cursor Device ID Modifier Tool{RESET}")
    print(f"  {YELLOW}Cursor ID Reset Tool - Community Edition{RESET}")
    print(f"  {YELLOW}Free tool for Cursor device ID management{RESET}")
    print(f"  {YELLOW}[IMPORTANT] This is a free community tool{RESET}")
    print(f"{BLUE}================================{RESET}")
    print(f"  {YELLOW}QQ群: 951642519 (交流/下载纯免费自动账号切换工具){RESET}")
    print()
    
    # 获取并显示 Cursor 版本
    cursor_version = get_cursor_version()
    if cursor_version:
        print(f"{GREEN}[INFO] Current Cursor version: v{cursor_version}{RESET}")
    else:
        print(f"{YELLOW}[WARNING] 无法检测 Cursor 版本{RESET}")
        print(f"{YELLOW}[TIP] 请确保 Cursor 已正确安装{RESET}")
    print()
    
    print(f"{YELLOW}[IMPORTANT NOTE] Latest 0.45.x (supported){RESET}")
    print()
    
    # 检查并关闭 Cursor 进程
    print(f"{GREEN}[INFO] 检查 Cursor 进程...{RESET}")
    close_cursor_process("Cursor")
    close_cursor_process("cursor")
    print()
    
    # 获取配置文件路径
    storage_file_path = get_storage_file_path()
    if not storage_file_path:
        print(f"{RED}[ERROR] 无法确定存储文件的 APPDATA 路径。{RESET}")
        press_enter_to_exit(1)
    
    # 获取备份目录路径
    backup_dir_path = get_backup_dir_path()
    if not backup_dir_path:
        print(f"{RED}[ERROR] 无法确定备份目录的 APPDATA 路径。{RESET}")
        press_enter_to_exit(1)
    
    # 创建备份目录
    if not backup_dir_path.exists():
        try:
            backup_dir_path.mkdir(parents=True, exist_ok=True)
            print(f"{GREEN}[INFO] 在 {backup_dir_path} 创建备份目录{RESET}")
        except Exception as e:
            print(f"{RED}[ERROR] 在 {backup_dir_path} 创建备份目录失败: {e}{RESET}")
            press_enter_to_exit(1)
    
    # 备份现有配置
    if storage_file_path.exists():
        print(f"{GREEN}[INFO] 备份配置文件...{RESET}")
        backup_name = f"storage.json.backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_file_path = backup_dir_path / backup_name
        try:
            shutil.copy2(storage_file_path, backup_file_path)
            print(f"{GREEN}[INFO] 配置已备份到 {backup_file_path}{RESET}")
        except Exception as e:
            print(f"{RED}[ERROR] 将配置文件备份到 {backup_file_path} 失败: {e}{RESET}")
    else:
        print(f"{GREEN}[INFO] 在 {storage_file_path} 未找到现有配置文件可备份。{RESET}")
    print()
    
    # 生成新 ID
    print(f"{GREEN}[INFO] 生成新 ID...{RESET}")
    mac_machine_id = new_standard_machine_id()
    uuid_str = str(uuid.uuid4())
    prefix_hex = ''.join(f"{b:02x}" for b in b"auth0|user_")
    random_part = get_random_hex(32)
    machine_id = f"{prefix_hex}{random_part}"
    sqm_id = f"{{{uuid.uuid4().hex.upper()}}}"
    print()
    
    # 更新注册表中的 MachineGuid
    machine_guid_updated = False
    if sys.platform == 'win32':
        machine_guid_updated = update_machine_guid(backup_dir_path)
    else:
        print(f"{YELLOW}[INFO] 跳过 MachineGuid 更新（非 Windows 系统）{RESET}")
    
    # 创建或更新配置文件
    print(f"{GREEN}[INFO] 更新配置...{RESET}")
    storage_update_successful = update_storage_file(
        storage_file_path,
        machine_id,
        mac_machine_id,
        uuid_str,  # 这对应于 PowerShell 中的 $UUID，即 devDeviceId
        sqm_id
    )
    
    if storage_update_successful:
        print(f"{GREEN}[INFO] 配置更新成功。{RESET}")
        # 显示结果
        print()
        print(f"{GREEN}[INFO] 配置更新详情:{RESET}")
        print(f"{BLUE}[DEBUG] machineId: {machine_id}{RESET}")
        print(f"{BLUE}[DEBUG] macMachineId: {mac_machine_id}{RESET}")
        print(f"{BLUE}[DEBUG] devDeviceId: {uuid_str}{RESET}")
        print(f"{BLUE}[DEBUG] sqmId: {sqm_id}{RESET}")
    else:
        print(f"{RED}[ERROR] 主操作更新存储文件失败。{RESET}")
        press_enter_to_exit(1)
    print()
    
    # 显示文件树结构
    print(f"{GREEN}[INFO] 文件结构:{RESET}")
    config_dir = appdirs.user_config_dir()
    cursor_user_dir = Path(config_dir) / "Cursor" / "User"
    print(f"{BLUE}{cursor_user_dir}{RESET}")
    print("├── globalStorage")
    print("│   ├── storage.json (modified)")
    print("│   └── backups")
    
    # 列出备份文件
    try:
        backup_files_found = False
        for entry in backup_dir_path.iterdir():
            if entry.is_file():
                print(f"│       └── {entry.name}")
                backup_files_found = True
        if not backup_files_found:
            print("│       └── (empty)")
    except Exception as e:
        print(f"│       └── (读取备份失败: {e})")
    print()
    
    # 显示完成消息
    print(f"{GREEN}================================{RESET}")
    print(f"  {YELLOW}Cursor ID Reset Tool - Community Edition{RESET}")
    print(f"{GREEN}================================{RESET}")
    print()
    print(f"{GREEN}[INFO] 请重启 Cursor 以应用新配置{RESET}")
    print()
    
    press_enter_to_exit(0)

if __name__ == "__main__":
    main()
