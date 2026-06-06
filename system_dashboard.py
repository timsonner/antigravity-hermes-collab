import os
import sys
import json
import socket
import datetime
import platform
import subprocess
import psutil

def format_bytes(bytes_val):
    if bytes_val is None:
        return "N/A"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} PB"

def get_system_stats():
    """Gathers Windows system metrics including CPU, RAM, Disk, and Page File settings."""
    stats = {}
    
    # 1. Host and OS information
    stats["hostname"] = socket.gethostname()
    stats["os_name"] = platform.system()
    stats["os_release"] = platform.release()
    stats["os_version"] = platform.version()
    stats["boot_time"] = datetime.datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
    stats["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 2. CPU model name via PowerShell CIM
    try:
        res = subprocess.run("powershell -Command \"(Get-CimInstance Win32_Processor).Name\"", shell=True, capture_output=True, text=True)
        stats["cpu_model"] = res.stdout.strip()
    except Exception:
        stats["cpu_model"] = platform.processor()
        
    # 3. CPU Core usage & metrics
    stats["cpu_percent"] = psutil.cpu_percent(interval=1.0)
    stats["cpu_cores_physical"] = psutil.cpu_count(logical=False)
    stats["cpu_cores_logical"] = psutil.cpu_count(logical=True)
    try:
        freq = psutil.cpu_freq()
        stats["cpu_frequency_mhz"] = f"{freq.current:.0f} MHz" if freq else "N/A"
    except Exception:
        stats["cpu_frequency_mhz"] = "N/A"
        
    # 4. RAM details
    ram = psutil.virtual_memory()
    stats["ram_total_raw"] = ram.total
    stats["ram_total"] = format_bytes(ram.total)
    stats["ram_used"] = format_bytes(ram.used)
    stats["ram_free"] = format_bytes(ram.available)
    stats["ram_percent"] = ram.percent
    
    # 5. Virtual Memory (Swap) details from psutil
    swap = psutil.swap_memory()
    stats["swap_total"] = format_bytes(swap.total)
    stats["swap_used"] = format_bytes(swap.used)
    stats["swap_percent"] = swap.percent
    
    # 6. Storage details (C:\ drive)
    try:
        disk = psutil.disk_usage('C:\\')
        stats["disk_total"] = format_bytes(disk.total)
        stats["disk_used"] = format_bytes(disk.used)
        stats["disk_free"] = format_bytes(disk.free)
        stats["disk_percent"] = disk.percent
    except Exception:
        stats["disk_total"] = "N/A"
        stats["disk_used"] = "N/A"
        stats["disk_free"] = "N/A"
        stats["disk_percent"] = 0.0
        
    # 7. Active Windows Page File configuration via CIM
    pagefiles = []
    
    # Get active page file usage details
    usage_stdout = ""
    try:
        res = subprocess.run("powershell -Command \"Get-CimInstance Win32_PageFileUsage | Select-Object Name, AllocatedBaseSize, CurrentUsage, PeakUsage | ConvertTo-Json\"", shell=True, capture_output=True, text=True)
        usage_stdout = res.stdout.strip()
    except Exception:
        pass
        
    usage_data = []
    if usage_stdout:
        try:
            parsed = json.loads(usage_stdout)
            if isinstance(parsed, dict):
                usage_data = [parsed]
            elif isinstance(parsed, list):
                usage_data = parsed
        except Exception:
            pass

    # Get active page file configured settings
    setting_stdout = ""
    try:
        res = subprocess.run("powershell -Command \"Get-CimInstance Win32_PageFileSetting | Select-Object Name, InitialSize, MaximumSize | ConvertTo-Json\"", shell=True, capture_output=True, text=True)
        setting_stdout = res.stdout.strip()
    except Exception:
        pass
        
    setting_data = {}
    if setting_stdout:
        try:
            parsed = json.loads(setting_stdout)
            if isinstance(parsed, dict):
                setting_list = [parsed]
            elif isinstance(parsed, list):
                setting_list = parsed
            else:
                setting_list = []
            for s in setting_list:
                name = s.get("Name", "").lower()
                if name:
                    setting_data[name] = s
        except Exception:
            pass

    for u in usage_data:
        name = u.get("Name", "Pagefile")
        allocated_mb = u.get("AllocatedBaseSize", 0)
        current_mb = u.get("CurrentUsage", 0)
        peak_mb = u.get("PeakUsage", 0)
        
        # Cross reference settings to see if it's auto-managed
        setting = setting_data.get(name.lower(), {})
        init_size = setting.get("InitialSize", 0)
        max_size = setting.get("MaximumSize", 0)
        
        is_auto = (allocated_mb > 0) and (not setting or (init_size == 0 and max_size == 0))
        
        usage_pct = (current_mb / allocated_mb * 100) if allocated_mb > 0 else 0
        peak_pct = (peak_mb / allocated_mb * 100) if allocated_mb > 0 else 0
        
        pagefiles.append({
            "name": name,
            "allocated_mb": allocated_mb,
            "allocated_str": f"{allocated_mb:,} MB",
            "current_mb": current_mb,
            "current_str": f"{current_mb:,} MB",
            "peak_mb": peak_mb,
            "peak_str": f"{peak_mb:,} MB",
            "init_size": init_size,
            "max_size": max_size,
            "is_auto": is_auto,
            "usage_pct": usage_pct,
            "peak_pct": peak_pct
        })
        
    if not pagefiles:
        # Fallback if no pagefile info returned
        pagefiles.append({
            "name": "None Detected or System Managed (Inactive)",
            "allocated_mb": 0,
            "allocated_str": "0 MB",
            "current_mb": 0,
            "current_str": "0 MB",
            "peak_mb": 0,
            "peak_str": "0 MB",
            "init_size": 0,
            "max_size": 0,
            "is_auto": True,
            "usage_pct": 0.0,
            "peak_pct": 0.0
        })
        
    stats["pagefiles"] = pagefiles
    return stats

def render_html_dashboard(stats, output_path):
    """Interpolates system statistics into a highly polished, dark-mode dashboard."""
    # Radial gauge stroke offsets (circumference of 251.32 px)
    def get_dashoffset(pct):
        circ = 251.32
        return circ - (pct / 100.0) * circ

    cpu_dashoffset = get_dashoffset(stats["cpu_percent"])
    ram_dashoffset = get_dashoffset(stats["ram_percent"])
    disk_dashoffset = get_dashoffset(stats["disk_percent"])
    
    # Generate Page File configuration cards HTML
    pagefiles_html = ""
    for pf in stats["pagefiles"]:
        badge = (
            '<span class="px-2.5 py-0.5 text-xs font-semibold rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">System Managed</span>'
            if pf["is_auto"] else
            '<span class="px-2.5 py-0.5 text-xs font-semibold rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">Custom Sizes</span>'
        )
        
        init_str = f"{pf['init_size']:,} MB" if pf['init_size'] > 0 else "System Managed"
        max_str = f"{pf['max_size']:,} MB" if pf['max_size'] > 0 else "System Managed"
        
        pagefiles_html += f"""
        <div class="p-5 rounded-xl border border-slate-700/50 bg-slate-800/40 backdrop-blur-md">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
                <div class="flex items-center gap-2">
                    <svg class="w-5 h-5 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <span class="text-sm font-semibold text-slate-200 truncate max-w-xs md:max-w-md title-path" title="{pf['name']}">{pf['name']}</span>
                </div>
                {badge}
            </div>
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <!-- Usage Meters -->
                <div>
                    <div class="flex justify-between items-center text-xs text-slate-400 mb-1.5">
                        <span>Current Active Usage</span>
                        <span class="font-semibold text-amber-400">{pf['current_str']} / {pf['allocated_str']} ({pf['usage_pct']:.1f}%)</span>
                    </div>
                    <div class="w-full bg-slate-900 rounded-full h-2.5 mb-4 overflow-hidden border border-slate-800">
                        <div class="bg-gradient-to-r from-amber-500 to-yellow-400 h-2.5 rounded-full transition-all duration-1000" style="width: {pf['usage_pct']}%"></div>
                    </div>
                    
                    <div class="flex justify-between items-center text-xs text-slate-400 mb-1.5">
                        <span>Peak Historic Usage</span>
                        <span class="font-semibold text-rose-400">{pf['peak_str']} ({pf['peak_pct']:.1f}%)</span>
                    </div>
                    <div class="w-full bg-slate-900 rounded-full h-2.5 overflow-hidden border border-slate-800">
                        <div class="bg-gradient-to-r from-rose-500 to-amber-500 h-2.5 rounded-full transition-all duration-1000" style="width: {pf['peak_pct']}%"></div>
                    </div>
                </div>
                
                <!-- Allocation Information -->
                <div class="grid grid-cols-2 gap-4 bg-slate-900/40 p-4 rounded-lg border border-slate-800/60">
                    <div>
                        <p class="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Initial Size Limit</p>
                        <p class="text-sm font-semibold text-slate-200 mt-1">{init_str}</p>
                    </div>
                    <div>
                        <p class="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Maximum Size Limit</p>
                        <p class="text-sm font-semibold text-slate-200 mt-1">{max_str}</p>
                    </div>
                    <div class="col-span-2 pt-2 border-t border-slate-800/80">
                        <p class="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Allocated Base Size</p>
                        <p class="text-base font-bold text-amber-400 mt-1">{pf['allocated_str']}</p>
                    </div>
                </div>
            </div>
        </div>
        """

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>System Status Dashboard</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        body {{
            font-family: 'Inter', sans-serif;
            background-color: #0b0f19;
        }}
        .glass-card {{
            background: rgba(30, 41, 59, 0.45);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.05);
            box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
        }}
        .glow-cyan {{
            filter: drop-shadow(0 0 8px rgba(6, 182, 212, 0.4));
        }}
        .glow-purple {{
            filter: drop-shadow(0 0 8px rgba(168, 85, 247, 0.4));
        }}
        .glow-emerald {{
            filter: drop-shadow(0 0 8px rgba(16, 185, 129, 0.4));
        }}
        .glow-amber {{
            filter: drop-shadow(0 0 8px rgba(245, 158, 11, 0.4));
        }}
        .title-path {{
            word-break: break-all;
        }}
    </style>
</head>
<body class="text-slate-300 min-h-screen p-4 md:p-8 flex flex-col justify-between">
    <div class="max-w-7xl mx-auto w-full space-y-8">
        
        <!-- Header -->
        <header class="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-800">
            <div>
                <div class="flex items-center gap-3">
                    <span class="w-3.5 h-3.5 rounded-full bg-emerald-500 animate-pulse glow-emerald"></span>
                    <h1 class="text-2xl md:text-3xl font-extrabold tracking-tight text-white bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">System Status</h1>
                </div>
                <p class="text-sm text-slate-400 mt-1">Premium dark-mode telemetry dashboard</p>
            </div>
            <div class="flex flex-wrap items-center gap-3 text-xs">
                <div class="glass-card px-4 py-2.5 rounded-lg flex items-center gap-2 border border-slate-800">
                    <span class="text-slate-500">Hostname:</span>
                    <span class="font-semibold text-slate-200">{stats["hostname"]}</span>
                </div>
                <div class="glass-card px-4 py-2.5 rounded-lg flex items-center gap-2 border border-slate-800">
                    <span class="text-slate-500">Generated:</span>
                    <span class="font-semibold text-cyan-400">{stats["timestamp"]}</span>
                </div>
            </div>
        </header>

        <!-- System Overview Grid -->
        <section class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div class="glass-card p-4 rounded-xl flex items-center gap-4">
                <div class="p-3 bg-cyan-500/10 rounded-lg border border-cyan-500/20 text-cyan-400">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                    </svg>
                </div>
                <div>
                    <p class="text-[11px] uppercase tracking-wider text-slate-500 font-bold">OS Version</p>
                    <p class="text-sm font-semibold text-slate-200">{stats["os_name"]} {stats["os_release"]}</p>
                    <p class="text-[10px] text-slate-500 truncate max-w-[250px]">{stats["os_version"]}</p>
                </div>
            </div>
            
            <div class="glass-card p-4 rounded-xl flex items-center gap-4">
                <div class="p-3 bg-purple-500/10 rounded-lg border border-purple-500/20 text-purple-400">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                    </svg>
                </div>
                <div>
                    <p class="text-[11px] uppercase tracking-wider text-slate-500 font-bold">CPU Model</p>
                    <p class="text-sm font-semibold text-slate-200 truncate max-w-[280px]" title="{stats['cpu_model']}">{stats['cpu_model']}</p>
                    <p class="text-[10px] text-slate-500">{stats['cpu_cores_physical']} Cores / {stats['cpu_cores_logical']} Threads</p>
                </div>
            </div>

            <div class="glass-card p-4 rounded-xl flex items-center gap-4">
                <div class="p-3 bg-emerald-500/10 rounded-lg border border-emerald-500/20 text-emerald-400">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                </div>
                <div>
                    <p class="text-[11px] uppercase tracking-wider text-slate-500 font-bold">System Boot Time</p>
                    <p class="text-sm font-semibold text-slate-200">{stats["boot_time"]}</p>
                    <p class="text-[10px] text-slate-500">Active telemetry session</p>
                </div>
            </div>
        </section>

        <!-- Metrics Gauges -->
        <main class="grid grid-cols-1 md:grid-cols-3 gap-6">
            
            <!-- CPU Gauge Card -->
            <div class="glass-card p-6 rounded-2xl flex flex-col justify-between border border-slate-800">
                <div class="flex items-center justify-between mb-4">
                    <div class="flex items-center gap-2">
                        <span class="w-2.5 h-2.5 rounded-full bg-cyan-500 glow-cyan"></span>
                        <h2 class="font-bold text-slate-200 text-base">CPU Utilization</h2>
                    </div>
                    <span class="text-xs bg-cyan-500/10 text-cyan-400 px-2.5 py-0.5 rounded-full border border-cyan-500/20 font-semibold">{stats["cpu_frequency_mhz"]}</span>
                </div>
                
                <div class="flex flex-col items-center justify-center my-6 relative">
                    <!-- Circular SVG Meter -->
                    <svg class="w-40 h-40 transform -rotate-90">
                        <circle cx="80" cy="80" r="40" class="stroke-slate-800/80" stroke-width="8" fill="transparent" />
                        <circle cx="80" cy="80" r="40" class="stroke-cyan-500 glow-cyan transition-all duration-1000" stroke-width="8" fill="transparent"
                                stroke-dasharray="251.32" stroke-dashoffset="{cpu_dashoffset}" stroke-linecap="round" />
                    </svg>
                    <div class="absolute flex flex-col items-center justify-center">
                        <span class="text-3xl font-extrabold text-white">{stats["cpu_percent"]:.1f}%</span>
                        <span class="text-[10px] uppercase tracking-widest text-slate-500 font-bold">Active Load</span>
                    </div>
                </div>

                <div class="border-t border-slate-800/80 pt-4 mt-2 grid grid-cols-2 gap-4 text-xs">
                    <div>
                        <span class="text-slate-500 block">Physical Cores</span>
                        <span class="font-bold text-slate-200 text-sm mt-0.5 block">{stats["cpu_cores_physical"]}</span>
                    </div>
                    <div>
                        <span class="text-slate-500 block">Logical Cores</span>
                        <span class="font-bold text-slate-200 text-sm mt-0.5 block">{stats["cpu_cores_logical"]}</span>
                    </div>
                </div>
            </div>

            <!-- RAM Gauge Card -->
            <div class="glass-card p-6 rounded-2xl flex flex-col justify-between border border-slate-800">
                <div class="flex items-center justify-between mb-4">
                    <div class="flex items-center gap-2">
                        <span class="w-2.5 h-2.5 rounded-full bg-purple-500 glow-purple"></span>
                        <h2 class="font-bold text-slate-200 text-base">Physical RAM</h2>
                    </div>
                    <span class="text-xs bg-purple-500/10 text-purple-400 px-2.5 py-0.5 rounded-full border border-purple-500/20 font-semibold">{stats["ram_total"]}</span>
                </div>
                
                <div class="flex flex-col items-center justify-center my-6 relative">
                    <!-- Circular SVG Meter -->
                    <svg class="w-40 h-40 transform -rotate-90">
                        <circle cx="80" cy="80" r="40" class="stroke-slate-800/80" stroke-width="8" fill="transparent" />
                        <circle cx="80" cy="80" r="40" class="stroke-purple-500 glow-purple transition-all duration-1000" stroke-width="8" fill="transparent"
                                stroke-dasharray="251.32" stroke-dashoffset="{ram_dashoffset}" stroke-linecap="round" />
                    </svg>
                    <div class="absolute flex flex-col items-center justify-center">
                        <span class="text-3xl font-extrabold text-white">{stats["ram_percent"]:.1f}%</span>
                        <span class="text-[10px] uppercase tracking-widest text-slate-500 font-bold">Utilized</span>
                    </div>
                </div>

                <div class="border-t border-slate-800/80 pt-4 mt-2 grid grid-cols-2 gap-4 text-xs">
                    <div>
                        <span class="text-slate-500 block">Used RAM</span>
                        <span class="font-bold text-slate-200 text-sm mt-0.5 block text-purple-400">{stats["ram_used"]}</span>
                    </div>
                    <div>
                        <span class="text-slate-500 block">Available RAM</span>
                        <span class="font-bold text-slate-200 text-sm mt-0.5 block text-emerald-400">{stats["ram_free"]}</span>
                    </div>
                </div>
            </div>

            <!-- Disk Gauge Card -->
            <div class="glass-card p-6 rounded-2xl flex flex-col justify-between border border-slate-800">
                <div class="flex items-center justify-between mb-4">
                    <div class="flex items-center gap-2">
                        <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 glow-emerald"></span>
                        <h2 class="font-bold text-slate-200 text-base">Disk Space (C:)</h2>
                    </div>
                    <span class="text-xs bg-emerald-500/10 text-emerald-400 px-2.5 py-0.5 rounded-full border border-emerald-500/20 font-semibold">{stats["disk_total"]}</span>
                </div>
                
                <div class="flex flex-col items-center justify-center my-6 relative">
                    <!-- Circular SVG Meter -->
                    <svg class="w-40 h-40 transform -rotate-90">
                        <circle cx="80" cy="80" r="40" class="stroke-slate-800/80" stroke-width="8" fill="transparent" />
                        <circle cx="80" cy="80" r="40" class="stroke-emerald-500 glow-emerald transition-all duration-1000" stroke-width="8" fill="transparent"
                                stroke-dasharray="251.32" stroke-dashoffset="{disk_dashoffset}" stroke-linecap="round" />
                    </svg>
                    <div class="absolute flex flex-col items-center justify-center">
                        <span class="text-3xl font-extrabold text-white">{stats["disk_percent"]:.1f}%</span>
                        <span class="text-[10px] uppercase tracking-widest text-slate-500 font-bold">Occupied</span>
                    </div>
                </div>

                <div class="border-t border-slate-800/80 pt-4 mt-2 grid grid-cols-2 gap-4 text-xs">
                    <div>
                        <span class="text-slate-500 block">Used Disk</span>
                        <span class="font-bold text-slate-200 text-sm mt-0.5 block text-rose-400">{stats["disk_used"]}</span>
                    </div>
                    <div>
                        <span class="text-slate-500 block">Free Disk</span>
                        <span class="font-bold text-slate-200 text-sm mt-0.5 block text-emerald-400">{stats["disk_free"]}</span>
                    </div>
                </div>
            </div>

        </main>

        <!-- Windows Page File Section -->
        <section class="glass-card p-6 rounded-2xl border border-slate-800/80 space-y-4">
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                    <span class="w-2.5 h-2.5 rounded-full bg-amber-500 glow-amber"></span>
                    <h2 class="text-lg font-bold text-slate-200">Active Windows Page File Configuration</h2>
                </div>
                <div class="text-[11px] text-slate-500 bg-slate-900/60 px-3 py-1.5 rounded border border-slate-800">
                    Virtual Memory (Swap): <span class="text-slate-300 font-semibold">{stats["swap_used"]} / {stats["swap_total"]} ({stats["swap_percent"]:.1f}%)</span>
                </div>
            </div>
            
            <div class="space-y-4">
                {pagefiles_html}
            </div>
        </section>

    </div>

    <!-- Footer -->
    <footer class="max-w-7xl mx-auto w-full text-center mt-12 pt-6 border-t border-slate-900/50 text-[11px] text-slate-600">
        <p>Telemetry system dashboard generated by Python & psutil. Designed for high performance monitoring.</p>
    </footer>
</body>
</html>
"""
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_template)

def main():
    dest_path = os.path.join(os.path.expanduser("~"), "system_status.html")
    print("Collecting system metrics...")
    stats = get_system_stats()
    
    print("Rendering HTML dashboard...")
    render_html_dashboard(stats, dest_path)
    print(f"SUCCESS: Premium system dashboard generated successfully at:\n  {dest_path}")

if __name__ == "__main__":
    main()
