import tkinter as tk
from tkinter import filedialog, ttk
import pandas as pd

# 창 생성
root = tk.Tk()
root.title("EntryChecker")
root.geometry("800x500")

# 파일 불러오기 함수
def load_excel_file():
    file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx;*.xls;*.xlsm")])
    if not file_path:
        return

    try:
        df = pd.read_excel(file_path, sheet_name=0, engine="openpyxl")
        df.fillna(0, inplace=True)  # 공백과 NaN 값을 0으로 채움

        # 모든 숫자 열을 정수로 변환
        for col in df.select_dtypes(include=['float', 'int']).columns:
            df[col] = df[col].astype(int)

        # '차변금액', '대변금액' 열을 1000 단위로 포맷팅
        if '차변금액' in df.columns:
            df['차변금액'] = df['차변금액'].apply(lambda x: f"{x:,}")
        if '대변금액' in df.columns:
            df['대변금액'] = df['대변금액'].apply(lambda x: f"{x:,}")
    except Exception as e:
        print(f"파일 로드 실패: {e}")
        return

    # 기존 Treeview 초기화
    tree.delete(*tree.get_children())
    tree["columns"] = list(df.columns)

    for col in df.columns:
        tree.heading(col, text=col)
        tree.column(col, anchor="center", width=150)  # 열 너비를 고정

    for _, row in df.iterrows():
        tree.insert("", "end", values=list(row))

# 버튼 영역
button_frame = tk.Frame(root)
button_frame.pack(side="top", anchor="w", pady=20, padx=20)  # 왼쪽 위로 고정

load_button = tk.Button(button_frame, text="파일 불러오기", command=load_excel_file)
load_button.pack()

# 프레임 구성 (Tree + Scroll)
frame = tk.Frame(root)
frame.pack(fill="both", expand=True, padx=(20, 20), pady=(20, 20))  # 오른쪽 여백 추가

# 스크롤바 먼저 생성 및 배치
scroll = ttk.Scrollbar(frame, orient="vertical")
scroll.pack(side="right", fill="y")

# Treeview 생성 시 yscrollcommand에 scroll.set 지정
tree = ttk.Treeview(frame, show="headings", yscrollcommand=scroll.set)
tree.pack(side="left", fill="both", expand=True)

# 스크롤바 커맨드에 Treeview의 yview 설정
scroll.configure(command=tree.yview)

# 실행
root.mainloop()
