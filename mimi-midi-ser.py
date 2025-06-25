# 使用方式：python mimi-midi-print.py C:\MIDI\python转串口脚本\mimi.mid
import mido
import time
import threading
from collections import deque
import argparse
import os
import serial
import serial.tools.list_ports

class MidiPlayer:
    def __init__(self, port=None, baudrate=115200):
        self.note_queue = deque()
        self.playing = False
        self.thread = None
        self.ser = None
        self.port = port
        self.baudrate = baudrate
        
        # 如果没有指定端口，自动选择第一个可用串口
        if port is None:
            ports = serial.tools.list_ports.comports()
            if ports:
                self.port = ports[0].device
                print(f"自动选择串口: {self.port}")
            else:
                print("警告: 未找到可用串口，将打印到控制台")
        
        # 尝试打开串口
        if self.port:
            try:
                self.ser = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.1
                )
                print(f"已连接到串口 {self.port} @ {baudrate} bps")
                # self.ser.write("reboot\r\n".encode('utf-8'))  # 发送重启命令"
            except serial.SerialException as e:
                print(f"无法打开串口 {self.port}: {e}")
                self.ser = None
        #延时500ms
        time.sleep(0.8)

    def _send_note(self, note, state="ON"):
        """通过串口发送音符命令"""
        # 格式化命令: "ON<note>\n" 或 "OFF<note>\n"
        # command = f"{state} {note}\n".encode('utf-8')
        # command = f"on {note}\n".encode('utf-8')
        
        # if self.ser and self.ser.is_open:
        #     try:
        #         self.ser.write(command)
        #         print(f"发送: {state} {note}")  # 调试输出
        #     except serial.SerialException as e:
        #         print(f"串口发送错误: {e}")
        # else:
        #     # 没有串口连接时打印到控制台
        #     print(f"{state}{note}")
        if state == "ON":
            # 格式化命令: "ON <note>\n"
            command = f"on {note}\r".encode('utf-8')
            
            if self.ser and self.ser.is_open:
                try:
                    self.ser.write(command)
                    print(command)  # 调试输出
                except serial.SerialException as e:
                    print(f"串口发送错误: {e}")
            else:
                # 没有串口连接时打印到控制台
                print(f"ON {note}")
        # 完全不发送OFF命令

    def _play_notes(self):
        """从队列中播放音符的线程函数"""
        last_time = 0
        while self.playing or self.note_queue:
            if self.note_queue:
                timestamp, note, state = self.note_queue.popleft()
                
                # 等待正确的时间
                delay = timestamp - last_time
                if delay > 0:
                    time.sleep(delay)
                last_time = timestamp
                
                self._send_note(note, state)
            else:
                time.sleep(0.001)  # 避免忙等待

    def load_midi(self, filepath):
        """加载并解析MIDI文件"""
        if not os.path.exists(filepath):
            print(f"错误: 文件 '{filepath}' 不存在")
            return False
        
        try:
            mid = mido.MidiFile(filepath)
            current_time = 0
            tempo = 500000  # 默认tempo (120 BPM)
            
            print(f"加载MIDI文件: {filepath}")
            print(f"MIDI信息: {len(mid.tracks)} 个音轨, {mid.length:.2f} 秒")
            print(f"每拍ticks数: {mid.ticks_per_beat}")
            
            total_notes = 0
            valid_notes = 0
            
            # 处理所有音轨
            for i, track in enumerate(mid.tracks):
                print(f"\n===== 处理音轨 {i+1} =====")
                track_time = 0
                for j, msg in enumerate(track):
                    track_time += msg.time
                    
                    # 更新速度（如果收到tempo变化事件）
                    if msg.type == 'set_tempo':
                        tempo = msg.tempo
                        print(f"消息 {j}: 速度变化 -> {60000000/tempo:.1f} BPM")
                    
                    # 处理音符事件
                    if msg.type in ['note_on', 'note_off']:
                        total_notes += 1
                        note_info = f"消息 {j}: {msg.type} 音符={msg.note}, 力度={msg.velocity}"
                        
                        # 只处理指定范围内的音符
                        if 24 <= msg.note <= 108:
                            # 计算真实时间（秒）
                            seconds = mido.tick2second(
                                track_time, 
                                mid.ticks_per_beat, 
                                tempo
                            )
                            
                            # 确定状态（ON=按下，OFF=释放）
                            state = "ON" if msg.type == 'note_on' and msg.velocity > 0 else "OFF"
                            
                            self.note_queue.append((seconds, msg.note, state))
                            print(f"{note_info} -> 有效 (时间={seconds:.2f}s)")
                            valid_notes += 1
                        else:
                            print(f"{note_info} -> 无效 (超出范围)")
            
            # 按时间排序所有音符事件
            self.note_queue = deque(sorted(self.note_queue, key=lambda x: x[0]))
            
            print(f"\n解析完成: 共找到 {total_notes} 个音符事件")
            print(f"有效音符: {valid_notes} 个 (24-108范围内)")
            return True
            
        except Exception as e:
            print(f"解析MIDI文件出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    def play(self):
        """开始播放MIDI"""
        if not self.note_queue:
            print("没有可播放的音符!")
            return
        
        self.playing = True
        self.thread = threading.Thread(target=self._play_notes)
        self.thread.daemon = True
        self.thread.start()
        print("开始播放... 按Ctrl+C停止")

    def stop(self):
        """停止播放"""
        self.playing = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        print("播放停止")
        
    def close(self):
        """关闭串口连接"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("串口连接已关闭")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='MIDI命令串口发送器')
    parser.add_argument('midi_file', help='MIDI文件路径')
    parser.add_argument('--port', '-p', help='串口端口 (例如 COM3 或 /dev/ttyUSB0)')
    parser.add_argument('--baud', '-b', type=int, default=115200, 
                        help='串口波特率 (默认 115200)')
    args = parser.parse_args()
    
    player = MidiPlayer(port=args.port, baudrate=args.baud)
    
    try:
        if player.load_midi(args.midi_file):
            player.play()
            
            # 等待播放完成（可按Ctrl+C停止）
            while player.thread and player.thread.is_alive():
                player.thread.join(0.1)
                
    except KeyboardInterrupt:
        print("\n用户请求停止...")
    finally:
        player.stop()
        player.close()