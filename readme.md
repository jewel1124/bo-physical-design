# BO_OPENROAD — Framework tự động tối ưu tham số flow thiết kế vật lý vi mạch

Framework tự động hóa quá trình Design Space Exploration (DSE) cho flow thiết kế vật lý vi mạch số sử dụng **LibreLane/OpenROAD**, áp dụng ba phương pháp tìm kiếm tham số: **Grid Search**, **Random Search** và **Bayesian Optimization**.

Đồ án: *Ứng dụng Bayesian Optimization để tối ưu tham số trong flow thiết kế vật lý vi mạch* — Đại học Bách Khoa Hà Nội.

---

## 1. Tổng quan các file

| File | Chức năng |
|---|---|
| `run_experiments.py` | Module lõi: cập nhật `config.json`, chạy LibreLane qua Docker, trích xuất metric, tính hàm chi phí. Đồng thời chạy **Grid Search** khi gọi trực tiếp (`python3 run_experiments.py`). |
| `run_bo.py` | Chạy **Bayesian Optimization** (dùng `scikit-optimize`), tái sử dụng `run_one()` từ `run_experiments.py`. |
| `run_random.py` | Chạy **Random Search** (baseline đối chứng cùng ngân sách với BO), cũng tái sử dụng `run_one()`. |

Cả ba script đều ghi log ra terminal, lưu dataset CSV tăng dần (incremental) sau mỗi lần chạy để tránh mất dữ liệu khi bị gián đoạn.

---

## 2. Yêu cầu hệ thống

- **OS**: Ubuntu 22.04 LTS (khuyến nghị) hoặc các bản Linux tương đương
- **Python**: 3.8 trở lên
- **Docker**: đã cài đặt và chạy được không cần `sudo` (xem mục 3.2)
- **Dung lượng đĩa trống**: tối thiểu ~20 GB (image Docker LibreLane + dữ liệu PDK + kết quả các lần chạy)
- **RAM**: khuyến nghị tối thiểu 8 GB
- **Thời gian chạy dự kiến**:
  - Grid Search (60 lần chạy): ~4.5 giờ
  - Random Search (10 lần chạy): ~0.7 giờ
  - Bayesian Optimization (10 lần chạy): ~0.8 giờ

---

## 3. Cài đặt môi trường

### 3.1. Cài Python và các thư viện cần thiết

```bash
sudo apt update
sudo apt install python3 python3-pip -y

pip3 install --upgrade pip
pip3 install pandas scikit-optimize
```

> `scikit-optimize` chỉ cần thiết cho `run_bo.py`. `pandas` được dùng ở cả ba script để đọc/ghi và lọc kết quả CSV.

### 3.2. Cài đặt Docker

```bash
sudo apt install docker.io -y
sudo systemctl enable --now docker

# Cho phép chạy docker không cần sudo (khuyến nghị)
sudo usermod -aG docker $USER
newgrp docker     # hoặc logout/login lại để áp dụng

# Kiểm tra
docker run hello-world
```

### 3.3. Cài đặt LibreLane (qua Docker image) và PDK

Pull image LibreLane đúng phiên bản đang dùng trong code (`2.4.13`):

```bash
docker pull ghcr.io/librelane/librelane:2.4.13
```

Framework cần thư mục `~/.ciel` chứa PDK (SkyWater 130nm) được mount vào container. Nếu chưa có, làm theo hướng dẫn cài đặt PDK chính thức của LibreLane:

```bash
pip3 install ciel
ciel enable --pdk-family sky130 <version_phù_hợp>
```

> Tham khảo tài liệu chính thức của LibreLane để biết version PDK tương thích với `librelane:2.4.13`.

### 3.4. Chuẩn bị thư mục làm việc (WORK_DIR)

Framework giả định bạn có sẵn một thư mục project LibreLane đã được khởi tạo, ví dụ:

```
/home/<user>/librelane_work/librelane/test/
├── designs/
│   └── APU/
│       ├── config.json
│       └── src/   (RTL Verilog)
```

Đây chính là thư mục tương ứng với lệnh `docker run ... -v <thư_mục_này>:/work ...` mà bạn thường dùng để chạy LibreLane thủ công.

---

## 4. Cấu hình trước khi chạy

Mở `run_experiments.py` và chỉnh các biến trong khối `USER CONFIG` cho đúng với máy của bạn:

```python
WORK_DIR = Path("/home/tuan/librelane_work/librelane/test")   # đổi thành đường dẫn thật của bạn
DESIGN_NAME = "APU"                                            # tên thiết kế
DOCKER_IMAGE = "ghcr.io/librelane/librelane:2.4.13"
TIMEOUT_SECONDS = 30 * 60                                       # timeout mỗi lần chạy (giây)
```

Cũng cần chỉnh đường dẫn mount `.ciel` trong hàm `make_command()` nếu thư mục PDK của bạn không nằm ở `/home/tuan/.ciel`:

```python
def make_command(tag):
    return [
        "docker", "run", "--rm",
        "-v", f"{WORK_DIR}:/work",
        "-v", "/home/tuan/.ciel:/home/librelane/.ciel",   # <-- đổi đường dẫn này
        "-v", "/home/tuan/.ciel:/root/.ciel",              # <-- và dòng này
        "-w", "/work",
        DOCKER_IMAGE,
        "librelane",
        f"designs/{DESIGN_NAME}/config.json",
        "--run-tag", tag,
    ]
```

Đảm bảo file `designs/APU/config.json` tồn tại tại `WORK_DIR` đã khai báo — framework sẽ tự backup file này thành `config.json.bak` trước khi bắt đầu chỉnh sửa, và bạn có thể khôi phục lại bất cứ lúc nào bằng cách copy ngược file `.bak` lại.

---

## 5. Hướng dẫn chạy

Chạy ba script độc lập theo thứ tự bất kỳ (không phụ thuộc lẫn nhau, ngoại trừ việc cùng ghi vào `config.json`, nên **không chạy song song cùng lúc**).

### 5.1. Grid Search (baseline — 60 lần chạy)

```bash
cd ~/BO_OPENROAD
python3 run_experiments.py
```

- Không gian tham số mặc định (chỉnh trong hàm `main()` của `run_experiments.py` nếu muốn thay đổi):
  ```python
  utils = [35, 40, 45, 50]
  aspect_ratios = [0.8, 1.0, 1.2]
  densities = [0.50, 0.55, 0.60, 0.65, 0.70]
  ```
- Kết quả lưu tại: `dataset/APU_dataset_3.csv`
- Log lỗi của các lần chạy thất bại lưu tại: `logs/<tag>.log`

### 5.2. Random Search (baseline cùng ngân sách với BO — 10 lần chạy)

```bash
python3 run_random.py
```

- Cấu hình: `N_CALLS = 10`, `RANDOM_SEED = 42` (chỉnh trong `run_random.py` nếu muốn thử seed khác)
- Kết quả lưu tại: `dataset/APU_random_dataset.csv`

### 5.3. Bayesian Optimization (phương pháp chính — 10 lần chạy)

```bash
python3 run_bo.py
```

- Cấu hình: `N_CALLS = 10`, `N_INITIAL_POINTS = 3`, acquisition `LCB` với `kappa = 2.5`
- Kết quả lưu tại: `dataset/APU_bo_dataset_3.csv`

> **Lưu ý quan trọng**: cả ba script đều dùng chung file `config.json` của thiết kế (ghi đè liên tục), nên **chỉ chạy một script tại một thời điểm**. Nếu cần chạy song song, hãy nhân bản thư mục `designs/APU` thành nhiều thư mục riêng (ví dụ `APU_gs`, `APU_rs`, `APU_bo`) và sửa `DESIGN_NAME`/`WORK_DIR` tương ứng cho từng bản sao.

---

## 6. Cấu trúc output sau khi chạy

```
BO_OPENROAD/
├── dataset/
│   ├── APU_dataset_3.csv          # Kết quả Grid Search
│   ├── APU_random_dataset.csv     # Kết quả Random Search
│   └── APU_bo_dataset_3.csv       # Kết quả Bayesian Optimization
├── logs/
│   └── <tag>.log                  # Log của các lần chạy failed/timeout
```

Mỗi dòng trong các file CSV gồm: tag cấu hình, ba tham số (`util`, `aspect_ratio`, `density`), trạng thái flow (`ok`/`failed`/`timeout`), thời gian chạy, các chỉ số PPA (`die_area`, `total_power`, `wirelength`, `wns`, `worst_slack`, `drc`) và giá trị hàm chi phí `cost`.

---

## 7. Một số sự cố thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `FileNotFoundError: Không tìm thấy WORK_DIR` | Sai đường dẫn `WORK_DIR` trong `run_experiments.py` | Kiểm tra lại đường dẫn tuyệt đối |
| Docker báo lỗi permission denied | User chưa thuộc group `docker` | Chạy `sudo usermod -aG docker $USER` rồi đăng nhập lại |
| Flow luôn `failed` ngay từ bước đầu | Thiếu PDK hoặc mount `.ciel` sai đường dẫn | Kiểm tra lại `make_command()` và đường dẫn `~/.ciel` |
| Một lần chạy bị treo lâu | Flow phức tạp hơn dự kiến hoặc deadlock trong tool | Đợi đến khi đạt `TIMEOUT_SECONDS`, script sẽ tự dừng và đánh dấu `timeout` |
| Mất dữ liệu giữa chừng khi tắt máy | — | Không đáng lo: dataset được lưu **incremental** sau mỗi lần chạy, có thể resume bằng cách bỏ qua các config đã có trong CSV (cần chỉnh thêm logic resume nếu muốn tự động hóa việc này) |
| `python3 run_random.py` chạy xong không in gì | Sai tên file hoặc file bị lưu thiếu nội dung | Kiểm tra `wc -l run_random.py`, đảm bảo khớp với file gốc |

---

## 8. Tham khảo nhanh tham số có thể chỉnh

| Tham số | Vị trí | Ý nghĩa |
|---|---|---|
| `TIMEOUT_SECONDS` | `run_experiments.py` | Thời gian tối đa cho mỗi lần chạy flow |
| `utils`, `aspect_ratios`, `densities` | `run_experiments.py` → `main()` | Lưới giá trị cho Grid Search |
| `N_CALLS`, `RANDOM_SEED` | `run_random.py` | Số lần chạy và hạt giống ngẫu nhiên của Random Search |
| `N_CALLS`, `N_INITIAL_POINTS`, `kappa` | `run_bo.py` | Ngân sách, số điểm khởi tạo, mức thăm dò của BO |
| `calc_cost()` | `run_experiments.py` | Công thức hàm chi phí và trọng số `w_A, w_P, w_τ, w_W` |

---

## 9. License & Ghi chú

Framework sử dụng các công cụ mã nguồn mở: Docker, LibreLane/OpenROAD, `scikit-optimize`, `pandas`. Mã nguồn các script (`run_experiments.py`, `run_bo.py`, `run_random.py`) được phát triển trong khuôn khổ đồ án tốt nghiệp tại Đại học Bách Khoa Hà Nội.