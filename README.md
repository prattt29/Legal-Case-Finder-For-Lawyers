🏛️ Legal Case Finder (GUI Version)

📖 Overview  
**Legal Case Finder** is a Python-based desktop application designed to **search legal case files** stored in PDF format.  
It allows users to search cases **by year and keyword**, and instantly view relevant matches through a clean **Graphical User Interface (GUI)** built using **Tkinter**.  

The project helps in managing large sets of legal documents arranged year-wise and retrieving them efficiently using **text-based search**.

⚙️ Features
✅ Search legal case files by **keyword** and/or **year**  
✅ Extract and index PDF content automatically  
✅ Display short **snippets** highlighting where the keyword appears  
✅ Open the matched PDF directly from the app  
✅ Simple and user-friendly **Tkinter GUI**  
✅ Lightweight **SQLite database** backend for fast search  


🧰 Technologies Used
| Component | Technology |
|------------|-------------|
| Programming Language | Python 3 |
| GUI Framework | Tkinter |
| Database | SQLite3 |
| PDF Processing | pdfplumber |
| File System | OS Module |

📁 Folder Structure
```
Legal-Case-Finder/
│
├── main.py                # Main Python script (GUI logic)
├── cases.db               # SQLite database (auto-generated)
├── /cases_by_year/        # Folder containing PDF case files by year
│   ├── 2019/
│   │   ├── case1.pdf
│   │   └── case2.pdf
│   ├── 2020/
│   │   ├── case1.pdf
│   │   └── case2.pdf
│   └── ...
│
├── /assets/               # Optional folder for icons or images
├── README.md              # Project documentation
└── requirements.txt       # Dependencies
```


🚀 Installation & Setup

Step 1: Clone the Repository
```bash
git clone https://github.com/<your-username>/Legal-Case-Finder.git
cd Legal-Case-Finder
```

Step 2: Install Required Libraries
```bash
pip install pdfplumber tkinter
```

Step 3: Prepare Your Case Files
Organize your case files in folders based on year:
```
/cases_by_year/2019/
    case1.pdf
    case2.pdf
/cases_by_year/2020/
    case3.pdf
```
Step 4: Run the Application
```bash
python main.py
```

---

🖥️ How It Works

1. **Launch the GUI**  
   Run the app and open the graphical interface.  

2. **Select Folder**  
   Choose the directory containing your year-wise PDF files.  

3. **Index PDFs**  
   The app extracts text using `pdfplumber` and stores it in an SQLite database.  

4. **Search Cases**  
   Enter a **keyword** and optional **year** to find relevant cases.  

5. **View & Open**  
   See matching cases in a list. Click on one to open the PDF directly.

---

## 🧠 Logical Flow

```
User Launches GUI
     ↓
Select Folder Containing PDFs
     ↓
Database Initialization (SQLite)
     ↓
Index PDFs → Extract Text → Store (year, name, content)
     ↓
User Enters Keyword + Year
     ↓
Search Database → Display Snippets
     ↓
Click Case → Open PDF in Default Viewer
```

---

## 🧩 Database Schema
| Column Name | Description |
|--------------|-------------|
| `year` | Year folder name of the case |
| `case_name` | PDF file name |
| `content` | Extracted text from the PDF |

---

## 🧪 Example Search
| Input | Output |
|--------|---------|
| Keyword: “judgment” | Shows all cases containing the word “judgment” |
| Keyword: “land dispute”, Year: “2020” | Shows 2020 cases with “land dispute” keyword |

---

## 📸 Screenshots (Optional)
_Add screenshots here after you run your GUI, e.g.:_
```
/assets/gui_home.png
/assets/gui_search.png
/assets/gui_results.png
```

---

## 👨‍💻 Author
**Prathmesh Parag Dhomane**  
🎓 MCA Student | 💼 Data & Tech Enthusiast  
📧 [Your Email Here]  
🌐 [GitHub Profile Link]

---

## 🏁 Future Improvements
- Add full-text search ranking  
- Highlight keyword in snippet  
- Add export option (PDF/CSV)  
- Add multiple keyword search support  

---

## 📜 License
This project is licensed under the **MIT License** — you are free to use, modify, and distribute it with proper attribution.
