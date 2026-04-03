import os
import sys
import json
import zipfile
import subprocess
import argparse
import platform
import tkinter as tk
from tkinter import filedialog, messagebox


def is_windows():
    return platform.system() == "Windows"

def is_linux():
    return platform.system() == "Linux"

def get_acl(path):
    if is_windows():
        # PowerShell для получения SDDL
        cmd = ['powershell', '-NoProfile', '-Command', f'(Get-Acl -LiteralPath "{path}").Sddl']
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout.strip()
    elif is_linux():
        # оставляем только сами права
        cmd = ['getfacl', '-c', path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout.strip()
    return ""

def set_acl(path, acl_data):
    if not acl_data:
        return
    if is_windows():
        # применяем к новому пути
        cmd = ['powershell', '-NoProfile', '-Command', 
               f'$sec = Get-Acl -LiteralPath "{path}"; $sec.SetSecurityDescriptorSddlForm("{acl_data}"); Set-Acl -LiteralPath "{path}" -AclObject $sec']
        subprocess.run(cmd, capture_output=True)
    elif is_linux():
        # передаем права
        cmd = ['setfacl', '--set-file=-', path]
        subprocess.run(cmd, input=acl_data, text=True, capture_output=True)


def serialize(input_path, output_path):
    input_path = os.path.abspath(input_path)
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Путь {input_path} не найден.")

    metadata = {"os": platform.system(), "permissions": {}}
    base_name = os.path.basename(input_path)
    base_dir = os.path.dirname(input_path)

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        if os.path.isfile(input_path):
            # 1 файл
            rel_path = base_name
            zipf.write(input_path, rel_path)
            metadata["permissions"][rel_path] = get_acl(input_path)
        else:
            # каталог
            for root, dirs, files in os.walk(input_path):
                # сохраняем права для папок
                for d in dirs:
                    full_dir_path = os.path.join(root, d)
                    rel_path = os.path.relpath(full_dir_path, base_dir)
                    zipf.write(full_dir_path, rel_path + '/')
                    metadata["permissions"][rel_path] = get_acl(full_dir_path)
                
                # для файлов
                for f in files:
                    full_file_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_file_path, base_dir)
                    zipf.write(full_file_path, rel_path)
                    metadata["permissions"][rel_path] = get_acl(full_file_path)
            
            metadata["permissions"][base_name] = get_acl(input_path)

        # метаданные в тот же архив
        zipf.writestr("metadata.json", json.dumps(metadata, indent=4))
    print(f"Успешно сохранено в {output_path}")

def deserialize(input_path, output_path):
    output_path = os.path.abspath(output_path)
    
    with zipfile.ZipFile(input_path, 'r') as zipf:
        if "metadata.json" not in zipf.namelist():
            raise ValueError("Файл metadata.json не найден в архиве")
        
        metadata = json.loads(zipf.read("metadata.json").decode('utf-8'))
        saved_os = metadata.get("os")
        current_os = platform.system()

        if saved_os != current_os:
            print(f"Архив создан в {saved_os}, а вы восстанавливаете в {current_os}")
            print("Права доступа могут быть несовместимы и будут пропущены")

        # извлекаем все файлы кроме metadata.json
        members = [m for m in zipf.namelist() if m != "metadata.json"]
        zipf.extractall(path=output_path, members=members)

        # применяем права
        if saved_os == current_os:
            for rel_path, acl_data in metadata["permissions"].items():
                target_path = os.path.join(output_path, rel_path)
                if os.path.exists(target_path):
                    set_acl(target_path, acl_data)
                    
    print(f"Успешно восстановлено в {output_path}")


class PermissionsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Менеджер прав доступа")
        self.geometry("400x300")
        self.eval('tk::PlaceWindow . center')

        tk.Label(self, text="Сериализация (Сохранение)", font=("Arial", 12, "bold")).pack(pady=10)
        
        tk.Button(self, text="Запаковать ФАЙЛ", command=self.gui_serialize_file, width=30).pack(pady=5)
        tk.Button(self, text="Запаковать КАТАЛОГ", command=self.gui_serialize_dir, width=30).pack(pady=5)
        
        tk.Frame(self, height=2, bd=1, relief=tk.SUNKEN).pack(fill=tk.X, padx=20, pady=15)
        
        tk.Label(self, text="Десериализация (Восстановление)", font=("Arial", 12, "bold")).pack(pady=10)
        tk.Button(self, text="Восстановить из файла", command=self.gui_deserialize, width=30).pack(pady=5)

    def gui_serialize_file(self):
        input_file = filedialog.askopenfilename(title="Выберите файл для сохранения")
        if not input_file: return
        output_file = filedialog.asksaveasfilename(title="Сохранить архив как...", defaultextension=".json", filetypes=[("All files", "*.*")])
        if not output_file: return
        self._run_task(serialize, input_file, output_file)

    def gui_serialize_dir(self):
        input_dir = filedialog.askdirectory(title="Выберите каталог для сохранения")
        if not input_dir: return
        output_file = filedialog.asksaveasfilename(title="Сохранить архив как...", defaultextension=".json", filetypes=[("All files", "*.*")])
        if not output_file: return
        self._run_task(serialize, input_dir, output_file)

    def gui_deserialize(self):
        input_file = filedialog.askopenfilename(title="Выберите архив для распаковки")
        if not input_file: return
        output_dir = filedialog.askdirectory(title="Выберите папку куда распаковать")
        if not output_dir: return
        self._run_task(deserialize, input_file, output_dir)

    def _run_task(self, func, *args):
        try:
            func(*args)
            messagebox.showinfo("Успех", "Операция выполнена успешно!")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Произошла ошибка:\n{str(e)}")

def main():
    parser = argparse.ArgumentParser(description="Сохранение и восстановление прав доступа к файлам и каталогам")
    parser.add_argument("--serialize", action="store_true", help="Режим сохранения")
    parser.add_argument("--deserialize", action="store_true", help="Режим восстановления")
    parser.add_argument("--input", type=str, help="Путь к входному файлу/каталогу")
    parser.add_argument("--output", type=str, help="Путь к выходному файлу/каталогу")

    args = parser.parse_args()

    if len(sys.argv) == 1:
        app = PermissionsApp()
        app.mainloop()
    elif args.serialize and args.input and args.output:
        serialize(args.input, args.output)
    elif args.deserialize and args.input and args.output:
        deserialize(args.input, args.output)
    else:
        print("Неверные параметры. Используйте --help для справки или запустите без параметров для GUI.")
        sys.exit(1)

if __name__ == "__main__":
    main()