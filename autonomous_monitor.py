#!/usr/bin/env python3
"""
Autonomous PatchWatch Monitoring Service
Runs independently with auto-confirmation enabled
"""

import sys
import time
from pathlib import Path

# Add the current directory to Python path
sys.path.append(str(Path(__file__).parent))

from monitoring_service import PatchWatchMonitoringService, load_monitoring_config

def run_autonomous_monitoring():
    """Run monitoring service autonomously with auto-confirmation"""
    print("🤖 Starting Autonomous PatchWatch Monitoring Service")
    print("=" * 60)
    
    # Load configuration with auto-confirmation
    config = load_monitoring_config()
    
    print(f"📋 Configuration Status:")
    print(f"   📁 Monitoring folder: {config.local_developer_folder}")
    print(f"   🌐 GitLab URL: {config.gitlab_url}")
    print(f"   👤 Author: {config.git_author_name} <{config.git_author_email}>")
    print(f"   ✅ Auto-confirm: {config.auto_confirm}")
    print(f"   🔄 Auto-sync: {config.auto_sync}")
    print(f"   🗑️ Auto-delete: {config.auto_delete}")
    print()
    
    if not config.auto_confirm:
        print("⚠️  WARNING: Auto-confirmation is disabled!")
        print("💡 To enable autonomous operation, set 'auto_confirm': true in working_config.json")
        print()
    
    # Create and start monitoring service
    service = PatchWatchMonitoringService(config)
    
    try:
        if service.start_monitoring():
            print("🚀 Autonomous monitoring started successfully!")
            print("🤖 System will automatically:")
            if config.auto_sync:
                print("   ✅ Sync new and modified files to GitLab")
            if config.auto_delete:
                print("   🗑️ Delete removed files from GitLab")
            print("   📝 Create detailed commit messages with full paths")
            print("   🔄 Process all changes without manual intervention")
            print()
            print("📊 Monitoring Status:")
            print(f"   👀 Watching: {config.local_developer_folder}")
            print(f"   🎯 Target: {config.gitlab_url}")
            print("   🔄 Status: Active and autonomous")
            print()
            print("💡 To stop monitoring, press Ctrl+C")
            print("🌐 Web interface available at: http://localhost:8085")
            print("-" * 60)
            
            # Keep running
            while service.is_running:
                time.sleep(1)
                
        else:
            print("❌ Failed to start autonomous monitoring")
            return False
            
    except KeyboardInterrupt:
        print("\n🛑 Stopping autonomous monitoring...")
        service.stop_monitoring()
        print("✅ Autonomous monitoring stopped")
        return True
    except Exception as e:
        print(f"❌ Error in autonomous monitoring: {e}")
        return False

def show_status():
    """Show current configuration status"""
    config = load_monitoring_config()
    
    print("📊 PatchWatch Autonomous Status")
    print("=" * 40)
    print(f"Auto-confirmation: {'🤖 ENABLED' if config.auto_confirm else '⚠️ DISABLED'}")
    print(f"Auto-sync: {'✅ ON' if config.auto_sync else '❌ OFF'}")
    print(f"Auto-delete: {'🗑️ ON' if config.auto_delete else '❌ OFF'}")
    print(f"Monitored folder: {config.local_developer_folder}")
    print(f"GitLab target: {config.gitlab_url}")
    print(f"Author: {config.git_author_name}")
    print()
    
    if config.auto_confirm and config.auto_sync:
        print("🎉 System ready for autonomous operation!")
    else:
        print("⚠️  Manual confirmation required for operations")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--status":
        show_status()
    else:
        run_autonomous_monitoring()
