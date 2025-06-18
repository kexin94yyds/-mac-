#!/usr/bin/env python3
"""
screen_time_checker.py
查询 macOS 应用使用时长工具
支持多种时间范围：24小时、7天、30天
"""

import os
import sqlite3
import sys
import json
from datetime import datetime, timedelta
from subprocess import run, PIPE
from collections import defaultdict

class ScreenTimeChecker:
    def __init__(self):
        self.db_path = os.path.expanduser(
            "~/Library/Application Support/Knowledge/knowledgeC.db"
        )
        self.epoch_offset = 978307200  # Mac→Unix 时间戳补偿
        
        # 应用名称缓存
        self.app_names = {}
        
    def check_database(self):
        """检查数据库是否存在且可访问"""
        if not os.path.exists(self.db_path):
            print(f"❌ 找不到数据库文件：{self.db_path}")
            print("请确保您在 macOS 上运行此脚本")
            return False
            
        try:
            conn = sqlite3.connect(self.db_path)
            conn.close()
            return True
        except sqlite3.OperationalError as e:
            print(f"❌ 无法访问数据库：{e}")
            print("\n💡 解决方法：")
            print("1. 打开 系统设置 → 隐私与安全性 → 完全磁盘访问")
            print("2. 点击 + 号添加 Terminal（或您运行此脚本的应用）")
            print("3. 重新运行脚本")
            return False
    
    def get_app_name(self, bundle_id):
        """获取应用的显示名称"""
        if bundle_id in self.app_names:
            return self.app_names[bundle_id]
        
        # 常见应用的映射
        common_apps = {
            'com.apple.Safari': 'Safari',
            'com.microsoft.VSCode': 'Visual Studio Code',
            'com.apple.finder': 'Finder',
            'com.apple.systempreferences': '系统设置',
            'com.tencent.xinWeChat': '微信',
            'com.apple.mail': '邮件',
            'com.apple.music': '音乐',
            'com.apple.tv': 'TV',
            'com.apple.photos': '照片',
            'com.apple.notes': '备忘录',
            'com.apple.reminders': '提醒事项',
            'com.apple.calendar': '日历',
            'com.apple.facetime': 'FaceTime',
            'com.apple.messages': '信息',
        }
        
        if bundle_id in common_apps:
            self.app_names[bundle_id] = common_apps[bundle_id]
            return common_apps[bundle_id]
        
        # 尝试从应用包获取名称
        app_name = bundle_id.split('.')[-1]
        
        # 尝试在 Applications 文件夹中查找
        app_paths = [
            f"/Applications/{app_name}.app",
            f"/System/Applications/{app_name}.app",
            f"/Applications/Utilities/{app_name}.app"
        ]
        
        for app_path in app_paths:
            if os.path.exists(app_path):
                try:
                    result = run([
                        "mdls", "-name", "kMDItemDisplayName", "-r", app_path
                    ], stdout=PIPE, stderr=PIPE, text=True, timeout=5)
                    
                    if result.returncode == 0 and result.stdout.strip():
                        display_name = result.stdout.strip()
                        if display_name != "(null)":
                            self.app_names[bundle_id] = display_name
                            return display_name
                except:
                    pass
        
        # 回退到 bundle_id 的最后一部分
        self.app_names[bundle_id] = app_name.title()
        return app_name.title()
    
    def get_usage_data(self, days=1):
        """获取指定天数内的应用使用数据"""
        if not self.check_database():
            return []
        
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            # 计算时间范围
            since = int((datetime.now() - timedelta(days=days)).timestamp()) - self.epoch_offset
            
            sql = """
            SELECT
              ZOBJECT.ZVALUESTRING AS bundle_id,
              SUM(ZOBJECT.ZENDDATE - ZOBJECT.ZSTARTDATE) AS seconds
            FROM ZOBJECT
            WHERE ZSTREAMNAME IN ('/app/usage','/app/inFocus')
              AND ZSTARTDATE > ?
              AND ZOBJECT.ZVALUESTRING IS NOT NULL
              AND ZOBJECT.ZVALUESTRING != ''
            GROUP BY bundle_id
            HAVING seconds > 60
            ORDER BY seconds DESC;
            """
            
            usage = cur.execute(sql, (since,)).fetchall()
            cur.close()
            conn.close()
            
            return usage
            
        except Exception as e:
            print(f"❌ 查询数据库时出错：{e}")
            return []
    
    def format_time(self, seconds):
        """格式化时间显示"""
        if seconds < 60:
            return f"{seconds:.0f}秒"
        elif seconds < 3600:
            return f"{seconds/60:.1f}分钟"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            if minutes > 0:
                return f"{hours:.0f}小时{minutes:.0f}分钟"
            else:
                return f"{hours:.1f}小时"
    
    def create_bar_chart(self, usage_data, max_width=30):
        """创建ASCII条形图"""
        if not usage_data:
            return []
        
        max_seconds = max(seconds for _, seconds in usage_data)  # 显示所有应用
        chart_lines = []
        
        for i, (bundle_id, seconds) in enumerate(usage_data):
            app_name = self.get_app_name(bundle_id)
            if len(app_name) > 15:
                app_name = app_name[:12] + "..."
            
            # 计算条形长度
            bar_length = int((seconds / max_seconds) * max_width)
            bar = "█" * bar_length + "░" * (max_width - bar_length)
            
            percentage = (seconds / sum(s for _, s in usage_data)) * 100
            time_str = self.format_time(seconds)
            
            chart_lines.append(f"{app_name:<15} {bar} {percentage:4.1f}% ({time_str})")
        
        return chart_lines
    
    def get_hourly_usage(self, days=1):
        """获取每小时使用情况"""
        if not self.check_database():
            return {}
        
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            since = int((datetime.now() - timedelta(days=days)).timestamp()) - self.epoch_offset
            
            sql = """
            SELECT
              ZOBJECT.ZVALUESTRING AS bundle_id,
              ZOBJECT.ZSTARTDATE + 978307200 AS start_time,
              ZOBJECT.ZENDDATE + 978307200 AS end_time,
              ZOBJECT.ZENDDATE - ZOBJECT.ZSTARTDATE AS duration
            FROM ZOBJECT
            WHERE ZSTREAMNAME IN ('/app/usage','/app/inFocus')
              AND ZSTARTDATE > ?
              AND ZOBJECT.ZVALUESTRING IS NOT NULL
              AND ZOBJECT.ZVALUESTRING != ''
              AND ZOBJECT.ZENDDATE - ZOBJECT.ZSTARTDATE > 60
            ORDER BY ZSTARTDATE;
            """
            
            records = cur.execute(sql, (since,)).fetchall()
            cur.close()
            conn.close()
            
            # 按小时统计
            hourly_usage = {}
            for i in range(24):
                hourly_usage[i] = 0
            
            for bundle_id, start_time, end_time, duration in records:
                start_hour = datetime.fromtimestamp(start_time).hour
                hourly_usage[start_hour] += duration
            
            return hourly_usage
            
        except Exception as e:
            print(f"❌ 查询每小时数据时出错：{e}")
            return {}
    
    def create_hourly_chart(self, hourly_usage, max_height=8):
        """创建每小时使用时间的ASCII图表"""
        if not hourly_usage:
            return []
        
        max_usage = max(hourly_usage.values()) if hourly_usage.values() else 1
        if max_usage == 0:
            max_usage = 1
        
        chart_lines = []
        
        # 从上到下画图表
        for level in range(max_height, 0, -1):
            line = ""
            for hour in range(24):
                usage = hourly_usage.get(hour, 0)
                height = int((usage / max_usage) * max_height)
                if height >= level:
                    line += "█"
                else:
                    line += " "
            chart_lines.append(line)
        
        # 添加时间标签
        hour_labels = ""
        for hour in range(0, 24, 3):
            hour_labels += f"{hour:2d}".ljust(3)
        
        chart_lines.append("-" * 24)
        chart_lines.append(hour_labels)
        
        return chart_lines
    
    def print_usage_report(self, days=1, debug=False, visual=False):
        """打印使用情况报告"""
        usage_data = self.get_usage_data(days)
        
        if not usage_data:
            print("😔 没有找到使用数据")
            return
        
        # 时间范围描述
        if days == 1:
            period = "过去 24 小时"
        elif days == 7:
            period = "过去 7 天"
        elif days == 30:
            period = "过去 30 天"
        else:
            period = f"过去 {days} 天"
        
        total_seconds = sum(seconds for _, seconds in usage_data)
        
        if visual:
            # iPhone风格的界面
            print("\n" + "─" * 60)
            print("🔋 电池".center(60))
            print("─" * 60)
            print(f"{period}".center(60))
            print()
            
            # 总使用时长 (大字体效果)
            time_str = self.format_time(total_seconds)
            print("屏幕总使用时间".center(60))
            print(f"{time_str}".center(60))
            print()
            
            # App使用情况条形图
            print("App的使用时长".center(60))
            print("─" * 60)
            
            chart_lines = self.create_bar_chart(usage_data)
            for line in chart_lines:
                print(f"  {line}")
            
            print("─" * 60)
            
        else:
            # 原始的列表风格
            print(f"\n📱 {period} 应用使用时长报告")
            print("=" * 50)
            
            print(f"📊 总使用时长：{self.format_time(total_seconds)}")
            
            if debug:
                print(f"🔍 调试信息：总秒数 = {total_seconds:.0f}, 总应用数 = {len(usage_data)}")
            
            print("-" * 50)
            
            displayed_seconds = 0
            for i, (bundle_id, seconds) in enumerate(usage_data, 1):
                app_name = self.get_app_name(bundle_id)
                percentage = (seconds / total_seconds) * 100
                
                print(f"{i:2d}. {app_name:<25} {self.format_time(seconds):>12} ({percentage:4.1f}%)")
                displayed_seconds += seconds
                
                if i >= 20:  # 只显示前20个应用
                    remaining = len(usage_data) - 20
                    if remaining > 0:
                        remaining_seconds = total_seconds - displayed_seconds
                        print(f"    ... 还有 {remaining} 个应用，剩余时长：{self.format_time(remaining_seconds)}")
                    break
            
            if debug and len(usage_data) <= 20:
                # 验证计算
                manual_total = sum(seconds for _, seconds in usage_data)
                print(f"\n🔍 计算验证：")
                print(f"   自动计算总时长: {total_seconds:.0f} 秒")
                print(f"   手动计算总时长: {manual_total:.0f} 秒")
                print(f"   显示的应用总时长: {displayed_seconds:.0f} 秒")
                if abs(total_seconds - manual_total) > 1:
                    print("   ⚠️ 计算可能有误差！")
    
    def export_to_json(self, days=1, filename=None):
        """导出数据到JSON文件"""
        usage_data = self.get_usage_data(days)
        
        if not usage_data:
            print("😔 没有找到可导出的数据")
            return
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screen_time_{days}days_{timestamp}.json"
        
        export_data = {
            "export_time": datetime.now().isoformat(),
            "period_days": days,
            "total_apps": len(usage_data),
            "apps": []
        }
        
        for bundle_id, seconds in usage_data:
            export_data["apps"].append({
                "bundle_id": bundle_id,
                "app_name": self.get_app_name(bundle_id),
                "usage_seconds": seconds,
                "usage_formatted": self.format_time(seconds)
            })
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 数据已导出到：{filename}")

def main():
    checker = ScreenTimeChecker()
    
    if len(sys.argv) == 1:
        # 默认显示iPhone风格的24小时使用情况
        checker.print_usage_report(1, visual=True)
    else:
        command = sys.argv[1].lower()
        
        if command in ['1', '24h', 'today']:
            checker.print_usage_report(1)
        elif command in ['7', '7d', 'week']:
            checker.print_usage_report(7)
        elif command in ['30', '30d', 'month']:
            checker.print_usage_report(30)
        elif command in ['v', 'visual', 'iphone']:
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 1
            checker.print_usage_report(days, visual=True)
        elif command == 'export':
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 1
            checker.export_to_json(days)
        elif command == 'debug':
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 1
            checker.print_usage_report(days, debug=True)
        elif command == 'help':
            print("""
🔍 macOS 屏幕使用时间查询工具

使用方法：
  python3 screen_time_checker.py [选项]

选项：
  (无参数)         显示过去24小时使用情况
  1, 24h, today    过去24小时
  7, 7d, week      过去7天
  30, 30d, month   过去30天
  v, visual, iphone [天数]  iPhone风格可视化界面
  debug [天数]     调试模式，显示详细计算信息
  export [天数]    导出JSON格式数据（默认1天）
  help             显示此帮助信息

示例：
  python3 screen_time_checker.py
  python3 screen_time_checker.py 7
  python3 screen_time_checker.py visual
  python3 screen_time_checker.py iphone 7
  python3 screen_time_checker.py debug 1
  python3 screen_time_checker.py export 7

注意：
  - 首次运行需要授予 Terminal "完全磁盘访问" 权限
  - 数据来源：~/Library/Application Support/Knowledge/knowledgeC.db
            """)
        else:
            try:
                days = int(command)
                checker.print_usage_report(days)
            except ValueError:
                print(f"❌ 未知命令：{command}")
                print("使用 'help' 查看帮助信息")

if __name__ == "__main__":
    main()