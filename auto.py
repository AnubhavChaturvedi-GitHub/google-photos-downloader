import os
import re
import logging
import requests
import pandas as pd
from pathlib import Path
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional
import time
from dataclasses import dataclass
import hashlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import queue
from datetime import datetime

# Configure logging
def setup_logging():
    log_filename = f"photo_downloader_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__), log_filename

@dataclass
class PhotoDownloadTask:
    """Data class to represent a photo download task"""
    name: str
    url: str
    file_path: Path

class AdvancedPhotoDownloader:
    """Advanced Google Photos downloader with concurrent processing and error handling"""
    
    def __init__(self, sheet_path: str, download_folder: str = "downloaded_photos", max_workers: int = 5, progress_callback=None):
        """
        Initialize the photo downloader
        
        Args:
            sheet_path: Path to the Google Sheet (CSV/Excel file)
            download_folder: Folder to save downloaded photos
            max_workers: Maximum number of concurrent downloads
            progress_callback: Callback function for progress updates
        """
        self.sheet_path = Path(sheet_path)
        self.download_folder = Path(download_folder)
        self.max_workers = max_workers
        self.progress_callback = progress_callback
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Create download folder if it doesn't exist
        self.download_folder.mkdir(exist_ok=True)
        
        # Statistics
        self.total_downloads = 0
        self.successful_downloads = 0
        self.failed_downloads = 0
        
    def load_sheet_data(self) -> pd.DataFrame:
        """
        Load data from Google Sheet (CSV/Excel file)
        
        Returns:
            DataFrame containing the sheet data
        """
        try:
            file_extension = self.sheet_path.suffix.lower()
            
            if file_extension == '.csv':
                df = pd.read_csv(self.sheet_path)
            elif file_extension in ['.xlsx', '.xls']:
                df = pd.read_excel(self.sheet_path)
            else:
                raise ValueError(f"Unsupported file format: {file_extension}")
            
            logger.info(f"Loaded sheet with {len(df)} rows")
            return df
            
        except Exception as e:
            logger.error(f"Error loading sheet: {e}")
            raise
    
    def extract_file_id_from_google_drive_url(self, url: str) -> Optional[str]:
        """
        Extract file ID from various Google Drive URL formats
        
        Args:
            url: Google Drive URL
            
        Returns:
            File ID if found, None otherwise
        """
        if not url or pd.isna(url):
            return None
            
        # Clean the URL
        url = str(url).strip()
        
        # Pattern for different Google Drive URL formats
        patterns = [
            r'/file/d/([a-zA-Z0-9-_]+)',  # https://drive.google.com/file/d/FILE_ID/view
            r'id=([a-zA-Z0-9-_]+)',       # https://drive.google.com/open?id=FILE_ID
            r'/d/([a-zA-Z0-9-_]+)',       # https://drive.google.com/uc?id=FILE_ID or /d/FILE_ID
            r'([a-zA-Z0-9-_]{25,})'       # Direct file ID (at least 25 characters)
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        logger.warning(f"Could not extract file ID from URL: {url}")
        return None
    
    def get_direct_download_url(self, file_id: str) -> str:
        """
        Convert Google Drive file ID to direct download URL
        
        Args:
            file_id: Google Drive file ID
            
        Returns:
            Direct download URL
        """
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    
    def sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename to be safe for filesystem
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename
        """
        # Remove or replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Remove leading/trailing spaces and dots
        filename = filename.strip(' .')
        
        # Limit length
        if len(filename) > 200:
            filename = filename[:200]
        
        return filename
    
    def get_file_extension_from_response(self, response: requests.Response) -> str:
        """
        Get file extension from response headers
        
        Args:
            response: HTTP response object
            
        Returns:
            File extension (with dot)
        """
        content_type = response.headers.get('content-type', '').lower()
        
        # Map content types to extensions
        type_map = {
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/bmp': '.bmp',
            'image/webp': '.webp',
            'image/tiff': '.tiff',
            'image/svg+xml': '.svg'
        }
        
        extension = type_map.get(content_type, '.jpg')  # Default to .jpg
        
        # Also check Content-Disposition header
        content_disposition = response.headers.get('content-disposition', '')
        if 'filename=' in content_disposition:
            try:
                filename_match = re.search(r'filename[^;=\n]*=(([\'"]).*?\2|[^;\n]*)', content_disposition)
                if filename_match:
                    filename = filename_match.group(1).strip('"\'')
                    file_ext = Path(filename).suffix
                    if file_ext:
                        extension = file_ext.lower()
            except:
                pass
        
        return extension
    
    def download_photo(self, task: PhotoDownloadTask) -> Tuple[bool, str]:
        """
        Download a single photo
        
        Args:
            task: PhotoDownloadTask object
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # Check if file already exists
            if task.file_path.exists():
                logger.info(f"File already exists, skipping: {task.file_path}")
                return True, f"Already exists: {task.name}"
            
            # Extract file ID from URL
            file_id = self.extract_file_id_from_google_drive_url(task.url)
            if not file_id:
                return False, f"Could not extract file ID from URL: {task.url}"
            
            # Get direct download URL
            download_url = self.get_direct_download_url(file_id)
            
            # Download the file
            logger.info(f"Downloading: {task.name} from {download_url}")
            
            response = self.session.get(download_url, timeout=30, stream=True)
            response.raise_for_status()
            
            # Check if we got redirected to Google's download warning page
            if 'accounts.google.com' in response.url or 'drive.google.com/uc' not in response.url:
                # Try alternative download method
                download_url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t"
                response = self.session.get(download_url, timeout=30, stream=True)
                response.raise_for_status()
            
            # Get file extension from response
            extension = self.get_file_extension_from_response(response)
            
            # Update file path with proper extension
            if not task.file_path.suffix:
                task.file_path = task.file_path.with_suffix(extension)
            
            # Download and save file
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            
            with open(task.file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
            
            # Verify download
            if task.file_path.exists() and task.file_path.stat().st_size > 0:
                logger.info(f"Successfully downloaded: {task.name} ({downloaded_size} bytes)")
                return True, f"Downloaded: {task.name}"
            else:
                return False, f"Download failed (empty file): {task.name}"
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error downloading {task.name}: {e}")
            return False, f"Network error: {task.name} - {str(e)}"
        except Exception as e:
            logger.error(f"Error downloading {task.name}: {e}")
            return False, f"Error: {task.name} - {str(e)}"
    
    def create_download_tasks(self, df: pd.DataFrame) -> List[PhotoDownloadTask]:
        """
        Create download tasks from DataFrame
        
        Args:
            df: DataFrame containing names and URLs
            
        Returns:
            List of PhotoDownloadTask objects
        """
        tasks = []
        
        # Detect column names (flexible column detection)
        name_columns = [col for col in df.columns if 'name' in col.lower()]
        url_columns = [col for col in df.columns if any(keyword in col.lower() 
                      for keyword in ['url', 'link', 'drive', 'photo'])]
        
        if not name_columns:
            logger.warning("No 'name' column found, using first column")
            name_column = df.columns[0]
        else:
            name_column = name_columns[0]
            
        if not url_columns:
            logger.warning("No URL column found, using second column")
            url_column = df.columns[1] if len(df.columns) > 1 else df.columns[0]
        else:
            url_column = url_columns[0]
        
        logger.info(f"Using columns - Name: '{name_column}', URL: '{url_column}'")
        
        for index, row in df.iterrows():
            name = str(row[name_column]).strip()
            url = str(row[url_column]).strip()
            
            # Skip empty rows
            if pd.isna(name) or pd.isna(url) or name == 'nan' or url == 'nan':
                continue
            
            # Sanitize filename
            safe_name = self.sanitize_filename(name)
            
            # Create file path
            file_path = self.download_folder / safe_name
            
            tasks.append(PhotoDownloadTask(name=name, url=url, file_path=file_path))
        
        logger.info(f"Created {len(tasks)} download tasks")
        return tasks
    
    def download_all_photos(self) -> dict:
        """
        Download all photos with concurrent processing
        
        Returns:
            Dictionary with download statistics
        """
        logger.info("Starting photo download process...")
        
        # Load sheet data
        df = self.load_sheet_data()
        
        # Create download tasks
        tasks = self.create_download_tasks(df)
        
        if not tasks:
            logger.warning("No download tasks created")
            return {"total": 0, "successful": 0, "failed": 0, "results": []}
        
        self.total_downloads = len(tasks)
        results = []
        
        # Process downloads with ThreadPoolExecutor
        logger.info(f"Starting concurrent downloads with {self.max_workers} workers...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_task = {executor.submit(self.download_photo, task): task for task in tasks}
            
            # Process completed tasks
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    success, message = future.result()
                    results.append({
                        "name": task.name,
                        "url": task.url,
                        "success": success,
                        "message": message
                    })
                    
                    if success:
                        self.successful_downloads += 1
                    else:
                        self.failed_downloads += 1
                    
                    # Progress update
                    completed = self.successful_downloads + self.failed_downloads
                    progress = (completed / self.total_downloads) * 100
                    
                    if self.progress_callback:
                        self.progress_callback(progress, completed, self.total_downloads, message)
                    
                    logger.info(f"Progress: {completed}/{self.total_downloads} - {message}")
                    
                except Exception as e:
                    logger.error(f"Task failed with exception: {e}")
                    self.failed_downloads += 1
                    results.append({
                        "name": task.name,
                        "url": task.url,
                        "success": False,
                        "message": f"Exception: {str(e)}"
                    })
        
        # Log final statistics
        logger.info(f"Download completed! Total: {self.total_downloads}, "
                   f"Successful: {self.successful_downloads}, Failed: {self.failed_downloads}")
        
        return {
            "total": self.total_downloads,
            "successful": self.successful_downloads,
            "failed": self.failed_downloads,
            "results": results
        }
    
    def save_results_report(self, results: dict, report_path: str = None):
        """
        Save download results to a CSV report
        
        Args:
            results: Results dictionary from download_all_photos
            report_path: Path to save the report
        """
        try:
            if report_path is None:
                report_path = f"download_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            df_report = pd.DataFrame(results["results"])
            df_report.to_csv(report_path, index=False)
            logger.info(f"Results report saved to: {report_path}")
            return report_path
        except Exception as e:
            logger.error(f"Error saving results report: {e}")
            return None

class PhotoDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Advanced Photo Downloader")
        self.root.geometry("800x700")
        self.root.minsize(600, 500)
        
        # Configure style
        style = ttk.Style()
        style.theme_use('clam')
        
        # Variables
        self.sheet_path_var = tk.StringVar()
        self.download_folder_var = tk.StringVar(value="downloaded_photos")
        self.max_workers_var = tk.IntVar(value=3)
        self.is_downloading = False
        
        # Initialize logger
        global logger
        logger, self.log_filename = setup_logging()
        
        self.setup_gui()
        
        # Center the window
        self.center_window()
    
    def center_window(self):
        """Center the window on the screen"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def setup_gui(self):
        """Setup the GUI components"""
        
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="Advanced Photo Downloader", 
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # File selection section
        file_frame = ttk.LabelFrame(main_frame, text="File Selection", padding="10")
        file_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        file_frame.columnconfigure(1, weight=1)
        
        ttk.Label(file_frame, text="Excel/CSV File:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        ttk.Entry(file_frame, textvariable=self.sheet_path_var, width=50).grid(row=0, column=1, 
                                                                               sticky=(tk.W, tk.E), 
                                                                               padx=(10, 5), pady=(0, 5))
        ttk.Button(file_frame, text="Browse", command=self.browse_file).grid(row=0, column=2, 
                                                                             pady=(0, 5))
        
        ttk.Label(file_frame, text="Download Folder:").grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        ttk.Entry(file_frame, textvariable=self.download_folder_var, width=50).grid(row=1, column=1, 
                                                                                    sticky=(tk.W, tk.E), 
                                                                                    padx=(10, 5), pady=(5, 0))
        ttk.Button(file_frame, text="Browse", command=self.browse_folder).grid(row=1, column=2, 
                                                                               pady=(5, 0))
        
        # Settings section
        settings_frame = ttk.LabelFrame(main_frame, text="Settings", padding="10")
        settings_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(settings_frame, text="Max Concurrent Downloads:").grid(row=0, column=0, sticky=tk.W)
        worker_spinbox = ttk.Spinbox(settings_frame, from_=1, to=10, textvariable=self.max_workers_var, 
                                    width=10)
        worker_spinbox.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        
        # Progress section
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding="10")
        progress_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        progress_frame.columnconfigure(0, weight=1)
        
        self.progress_var = tk.StringVar(value="Ready to start...")
        self.progress_label = ttk.Label(progress_frame, textvariable=self.progress_var)
        self.progress_label.grid(row=0, column=0, sticky=tk.W)
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress_bar.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
        
        # Control buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=3, pady=(0, 10))
        
        self.start_button = ttk.Button(button_frame, text="Start Download", 
                                      command=self.start_download, style='Accent.TButton')
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_button = ttk.Button(button_frame, text="Stop", command=self.stop_download, 
                                     state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(button_frame, text="Open Download Folder", 
                  command=self.open_download_folder).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(button_frame, text="View Log", command=self.view_log).pack(side=tk.LEFT)
        
        # Log display section
        log_frame = ttk.LabelFrame(main_frame, text="Download Log", padding="10")
        log_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(5, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, 
                              padding="5")
        status_bar.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E))
    
    def browse_file(self):
        """Browse for Excel/CSV file"""
        filename = filedialog.askopenfilename(
            title="Select Excel or CSV file",
            filetypes=[
                ("Excel files", "*.xlsx *.xls"),
                ("CSV files", "*.csv"),
                ("All files", "*.*")
            ]
        )
        if filename:
            self.sheet_path_var.set(filename)
    
    def browse_folder(self):
        """Browse for download folder"""
        folder = filedialog.askdirectory(title="Select download folder")
        if folder:
            self.download_folder_var.set(folder)
    
    def open_download_folder(self):
        """Open the download folder in file explorer"""
        folder_path = self.download_folder_var.get()
        if folder_path and os.path.exists(folder_path):
            os.startfile(folder_path) if os.name == 'nt' else os.system(f'open "{folder_path}"')
        else:
            messagebox.showwarning("Warning", "Download folder does not exist!")
    
    def view_log(self):
        """Open the log file"""
        if os.path.exists(self.log_filename):
            os.startfile(self.log_filename) if os.name == 'nt' else os.system(f'open "{self.log_filename}"')
        else:
            messagebox.showinfo("Info", "Log file not found!")
    
    def log_message(self, message):
        """Add message to log display"""
        self.log_text.insert(tk.END, f"{datetime.now().strftime('%H:%M:%S')} - {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def progress_callback(self, progress, completed, total, message):
        """Callback for progress updates"""
        self.progress_bar['value'] = progress
        self.progress_var.set(f"Progress: {completed}/{total} ({progress:.1f}%)")
        self.status_var.set(message)
        self.log_message(f"{completed}/{total}: {message}")
        self.root.update_idletasks()
    
    def validate_inputs(self):
        """Validate user inputs"""
        if not self.sheet_path_var.get():
            messagebox.showerror("Error", "Please select an Excel or CSV file!")
            return False
        
        if not os.path.exists(self.sheet_path_var.get()):
            messagebox.showerror("Error", "Selected file does not exist!")
            return False
        
        if not self.download_folder_var.get():
            messagebox.showerror("Error", "Please specify a download folder!")
            return False
        
        return True
    
    def start_download(self):
        """Start the download process"""
        if not self.validate_inputs():
            return
        
        self.is_downloading = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        
        # Clear log
        self.log_text.delete(1.0, tk.END)
        
        # Reset progress
        self.progress_bar['value'] = 0
        self.progress_var.set("Starting download...")
        self.status_var.set("Initializing...")
        
        # Start download in separate thread
        thread = threading.Thread(target=self.download_worker)
        thread.daemon = True
        thread.start()
    
    def download_worker(self):
        """Worker function for downloads"""
        try:
            self.log_message("Initializing downloader...")
            
            # Create downloader
            downloader = AdvancedPhotoDownloader(
                sheet_path=self.sheet_path_var.get(),
                download_folder=self.download_folder_var.get(),
                max_workers=self.max_workers_var.get(),
                progress_callback=self.progress_callback
            )
            
            self.log_message(f"Starting downloads with {self.max_workers_var.get()} workers...")
            
            # Start downloads
            results = downloader.download_all_photos()
            
            # Save report
            report_path = downloader.save_results_report(results)
            
            # Update GUI
            self.root.after(0, self.download_completed, results, report_path)
            
        except Exception as e:
            error_msg = f"Download failed: {str(e)}"
            self.log_message(error_msg)
            self.root.after(0, self.download_failed, error_msg)
    
    def download_completed(self, results, report_path):
        """Handle download completion"""
        self.is_downloading = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        
        total = results['total']
        successful = results['successful']
        failed = results['failed']
        success_rate = (successful / total * 100) if total > 0 else 0
        
        self.progress_var.set(f"Completed: {successful}/{total} successful ({success_rate:.1f}%)")
        self.status_var.set("Download completed!")
        
        self.log_message("=" * 50)
        self.log_message("DOWNLOAD SUMMARY")
        self.log_message("=" * 50)
        self.log_message(f"Total photos: {total}")
        self.log_message(f"Successfully downloaded: {successful}")
        self.log_message(f"Failed downloads: {failed}")
        self.log_message(f"Success rate: {success_rate:.1f}%")
        self.log_message(f"Photos saved in: {self.download_folder_var.get()}")
        if report_path:
            self.log_message(f"Report saved: {report_path}")
        
        # Show completion message
        messagebox.showinfo("Download Complete", 
                           f"Download completed!\n\n"
                           f"Total: {total}\n"
                           f"Successful: {successful}\n"
                           f"Failed: {failed}\n"
                           f"Success Rate: {success_rate:.1f}%")
    
    def download_failed(self, error_msg):
        """Handle download failure"""
        self.is_downloading = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        
        self.progress_var.set("Download failed!")
        self.status_var.set("Error occurred")
        
        messagebox.showerror("Download Failed", error_msg)
    
    def stop_download(self):
        """Stop the download process"""
        if self.is_downloading:
            # Note: This is a simple implementation. 
            # For a more robust solution, you'd need to implement proper thread cancellation
            self.is_downloading = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.status_var.set("Download stopped by user")
            self.log_message("Download stopped by user")

def main():
    """Main function to run the GUI application"""
    root = tk.Tk()
    app = PhotoDownloaderGUI(root)
    
    # Handle window closing
    def on_closing():
        if app.is_downloading:
            if messagebox.askokcancel("Quit", "Download in progress. Do you want to quit?"):
                root.destroy()
        else:
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    # Start the GUI
    root.mainloop()

if __name__ == "__main__":
    main()