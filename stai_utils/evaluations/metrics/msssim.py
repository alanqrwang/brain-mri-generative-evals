import torch
from generative.metrics import MultiScaleSSIMMetric


def compute_pairwise_msssim(loader, N=1000):
    tot_metric = 0
    count = 0
    msssim = MultiScaleSSIMMetric(spatial_dims=3, kernel_size=9)
    for i, data1 in enumerate(loader):
        for j, data2 in enumerate(loader):
            if count >= N:
                break
            if i != j:
                img1 = data1["vol_data"].float()
                img2 = data2["vol_data"].float()
                tot_metric += msssim(img1, img2).item()
                count += 1

    return tot_metric / count
