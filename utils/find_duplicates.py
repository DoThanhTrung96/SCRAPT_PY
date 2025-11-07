#!/usr/bin/env python3
"""
Find duplicate files in a directory by comparing names and extensions.
Also provides information about the duplicates found.
"""

import os
from pathlib import Path
from collections import defaultdict
import argparse
from datetime import datetime
import json

class DuplicateFinder:
    def __init__(self, target_dir):
        self.target_dir = Path(target_dir)
        if not self.target_dir.exists():
            raise ValueError(f"Directory does not exist: {target_dir}")
        
        self.duplicates = defaultdict(list)
        self.total_files = 0
        self.duplicate_sets = 0
        
    def scan_for_duplicates(self):
        """Scan the directory for files with duplicate names."""
        print(f"Scanning directory: {self.target_dir}")
        
        # Reset counters
        self.duplicates.clear()
        self.total_files = 0
        self.duplicate_sets = 0
        
        # Walk through the directory
        for root, _, files in os.walk(self.target_dir):
            for filename in files:
                self.total_files += 1
                file_path = Path(root) / filename
                
                # Use the filename as the key for duplicate detection
                self.duplicates[filename].append({
                    'path': str(file_path),
                    'size': file_path.stat().st_size,
                    'modified': datetime.fromtimestamp(file_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
        
        # Remove entries that don't have duplicates
        self.duplicates = {k: v for k, v in self.duplicates.items() if len(v) > 1}
        self.duplicate_sets = len(self.duplicates)
        
    def print_report(self):
        """Print a detailed report of the duplicates found."""
        print("\n=== Duplicate Files Report ===")
        print(f"Total files scanned: {self.total_files}")
        print(f"Number of duplicate sets found: {self.duplicate_sets}")
        
        if self.duplicate_sets == 0:
            print("\nNo duplicates found!")
            return
        
        print("\nDuplicate files found:")
        print("=" * 80)
        
        for filename, copies in self.duplicates.items():
            print(f"\nFilename: {filename}")
            print("-" * 40)
            for copy in copies:
                print(f"  Location: {copy['path']}")
                print(f"  Size: {copy['size']} bytes")
                print(f"  Modified: {copy['modified']}")
                print()
    
    def save_report(self, output_file):
        """Save the duplicate report to a JSON file."""
        report = {
            'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'target_directory': str(self.target_dir),
            'total_files': self.total_files,
            'duplicate_sets': self.duplicate_sets,
            'duplicates': self.duplicates
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\nReport saved to: {output_file}")
    
    def remove_duplicates(self, keep_newest=True):
        """Remove duplicate files, keeping either the newest or oldest version."""
        if not self.duplicates:
            print("No duplicates to remove!")
            return
        
        removed_count = 0
        saved_space = 0
        
        print("\nRemoving duplicates...")
        for filename, copies in self.duplicates.items():
            # Sort copies by modification time
            sorted_copies = sorted(copies, key=lambda x: os.path.getmtime(x['path']), 
                                reverse=keep_newest)
            
            # Keep the first one (either newest or oldest)
            keeper = sorted_copies[0]
            to_remove = sorted_copies[1:]
            
            print(f"\nFor {filename}:")
            print(f"Keeping: {keeper['path']}")
            print("Removing:")
            
            for copy in to_remove:
                try:
                    file_size = os.path.getsize(copy['path'])
                    os.remove(copy['path'])
                    print(f"- {copy['path']}")
                    removed_count += 1
                    saved_space += file_size
                except Exception as e:
                    print(f"Error removing {copy['path']}: {e}")
        
        print(f"\nRemoval complete!")
        print(f"Files removed: {removed_count}")
        print(f"Space saved: {saved_space / (1024*1024):.2f} MB")
        
        # Rescan to update the duplicates list
        self.scan_for_duplicates()

def main():
    parser = argparse.ArgumentParser(description='Find duplicate files by name in a directory.')
    parser.add_argument('directory', help='Directory to scan for duplicates')
    parser.add_argument('--output', '-o', help='Save report to JSON file')
    parser.add_argument('--remove', '-r', action='store_true', help='Remove duplicate files')
    parser.add_argument('--keep-oldest', action='store_true', help='Keep oldest files instead of newest when removing')
    args = parser.parse_args()
    
    try:
        finder = DuplicateFinder(args.directory)
        finder.scan_for_duplicates()
        finder.print_report()
        
        if args.output:
            finder.save_report(args.output)
        
        if args.remove:
            if input("\nAre you sure you want to remove duplicates? This cannot be undone! (y/N): ").lower() == 'y':
                finder.remove_duplicates(keep_newest=not args.keep_oldest)
            else:
                print("Removal cancelled.")
            
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())