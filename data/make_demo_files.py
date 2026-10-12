"""生成演示用数据文件：normal_rows.txt / attack_rows.txt
从 NF-UNSW-NB15-v3-test-split.csv 切分并重写 IP 为车联网场景地址。
"""
import csv
import random
from collections import defaultdict

SRC = "NF-UNSW-NB15-v3-test-split.csv"
NORMAL_OUT = "normal_rows.txt"
ATTACK_OUT = "attack_rows.txt"

N_NORMAL = 600
N_ATTACK = 600

random.seed(42)

# 车辆 IP 池（车联网场景）
VEHICLE_IPS = [f"192.168.1.{10 + i}" for i in range(1, 21)]  # .11-.30 车辆
DC_IP = "192.168.1.100"  # 数据中心网关
ATTACKER_IP = "192.168.1.200"  # 攻击者

def rewrite_ip(src, dst):
    """把数据集的 IP 改写成车联网场景 IP"""
    # 数据集里源/目的 IP 都是 59.166.0.x，全部映射到车辆/数据中心
    new_src = random.choice(VEHICLE_IPS)
    new_dst = DC_IP if random.random() < 0.7 else random.choice(VEHICLE_IPS)
    return new_src, new_dst

def main():
    with open(SRC, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)

        normals = []
        attacks = defaultdict(list)
        for row in reader:
            if row[-1] == 'Benign':
                normals.append(row)
            else:
                attacks[row[-1]].append(row)

    print(f"正常行: {len(normals)}, 攻击行: {sum(len(v) for v in attacks.values())}")

    # 取正常样本
    random.shuffle(normals)
    normal_sample = normals[:N_NORMAL]

    # 取攻击样本（混合各类型，保持一定比例）
    attack_sample = []
    # 按 4:3:2:1 比例混合主要攻击类型
    target_dist = {'Exploits': 0.35, 'Fuzzers': 0.25, 'Generic': 0.15,
                   'Reconnaissance': 0.15, 'DoS': 0.10}
    for atk, ratio in target_dist.items():
        pool = attacks.get(atk, [])
        n = int(N_ATTACK * ratio)
        random.shuffle(pool)
        attack_sample.extend(pool[:n])
    # 补充其他类型凑够数
    others = [r for k, v in attacks.items() if k not in target_dist for r in v]
    random.shuffle(others)
    need = N_ATTACK - len(attack_sample)
    attack_sample.extend(others[:need])
    random.shuffle(attack_sample)

    # 写正常文件
    with open(NORMAL_OUT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in normal_sample:
            src, dst = rewrite_ip(row[2], row[4])
            row[2], row[4] = src, dst
            writer.writerow(row)
    print(f"已写 {NORMAL_OUT}: {len(normal_sample)} 行")

    # 写攻击文件
    with open(ATTACK_OUT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in attack_sample:
            # 攻击源是攻击者或被劫持车辆
            if random.random() < 0.6:
                row[2] = ATTACKER_IP  # 外部攻击者
            else:
                row[2] = random.choice(VEHICLE_IPS)  # 被劫持的车辆
            row[4] = random.choice([DC_IP] + VEHICLE_IPS)
            writer.writerow(row)
    print(f"已写 {ATTACK_OUT}: {len(attack_sample)} 行")

if __name__ == "__main__":
    main()
