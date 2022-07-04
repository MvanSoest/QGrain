import logging
import time
import typing

import numpy as np
import torch

from ..emma import KERNEL_CLASS_MAP, KernelType, Proportion
from ..model import GrainSizeDataset
from ._result import UDMResult
from ._setting import UDMAlgorithmSetting


class UDMModule(torch.nn.Module):
    def __init__(self,
                 n_samples: int,
                 n_components: int,
                 classes_φ: np.ndarray,
                 kernel_type: KernelType,
                 parameters: np.ndarray = None):
        super().__init__()
        self.n_samples = n_samples
        self.n_components = n_components
        self.n_classes = len(classes_φ)
        self.interval = np.abs((classes_φ[0]-classes_φ[-1]) / (classes_φ.shape[0]-1))
        self.classes = torch.nn.Parameter(torch.from_numpy(classes_φ).repeat(n_samples, n_components, 1), requires_grad=False)
        self.kernel_type = kernel_type
        kernel_class = KERNEL_CLASS_MAP[kernel_type]
        self.proportions = Proportion(n_samples, n_components)
        self.components = kernel_class(n_samples, self.n_components, self.n_classes, parameters)

    def forward(self):
        # n_samples x 1 x n_members
        proportions = self.proportions()
        # n_samples x n_members x n_classes
        components = self.components(self.classes, self.interval)
        return proportions, components


class UDMResolver:
    logger = logging.getLogger("QGrain.UDMResolver")
    def __init__(self):
        pass

    def try_fit(self, dataset: GrainSizeDataset,
                kernel_type: KernelType,
                n_components: int,
                resolver_setting: UDMAlgorithmSetting = None,
                parameters: np.ndarray = None) -> UDMResult:
        if resolver_setting is None:
            s = UDMAlgorithmSetting()
        else:
            assert isinstance(resolver_setting, UDMAlgorithmSetting)
            s = resolver_setting

        X = torch.from_numpy(dataset.distribution_matrix.astype(np.float32)).to(s.device)
        classes_φ = dataset.classes_φ.astype(np.float32)
        udm = UDMModule(dataset.n_samples, n_components, classes_φ, kernel_type, parameters).to(s.device)
        optimizer = torch.optim.Adam(udm.parameters(), lr=s.learning_rate, betas=s.betas)

        start = time.time()
        distribution_loss_series = []
        component_loss_series = []
        history = []
        udm.components.requires_grad = False
        udm.components.params.requires_grad = False
        for pretrain_epoch in range(s.pretrain_epochs):
            proportions, components = udm()
            X_hat = (proportions @ components).squeeze(1)
            distribution_loss = torch.log10(torch.mean(torch.square(X - X_hat)))
            distribution_loss_series.append(distribution_loss.item())
            component_loss_series.append(0.0)
            optimizer.zero_grad()
            distribution_loss.backward()
            optimizer.step()
            params = torch.cat([udm.components.params, udm.proportions.params], dim=1).detach().cpu().numpy()
            history.append(params)

        udm.components.requires_grad = True
        udm.components.params.requires_grad = True
        for epoch in range(s.max_epochs):
            # train
            proportions, components = udm()
            X_hat = (proportions @ components).squeeze(1)
            distribution_loss = torch.log10(torch.mean(torch.square(X_hat - X)))
            component_loss = torch.mean(torch.std(components, dim=0))
            loss = distribution_loss + (10**s.constraint_level) * component_loss

            if np.isnan(loss.item()):
                self.logger.warning("Loss is NaN, training terminated.")
                break

            distribution_loss_series.append(distribution_loss.item())
            component_loss_series.append((10**s.constraint_level) * component_loss.item())
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            params = torch.cat([udm.components.params, udm.proportions.params], dim=1).detach().cpu().numpy()
            history.append(params)

            if epoch > s.min_epochs:
                delta_loss = np.mean(distribution_loss_series[-100:-80])-np.mean(distribution_loss_series[-20:])
                if delta_loss < 10**(-s.precision):
                    break

        if s.device == "cuda":
            torch.cuda.synchronize()
        time_spent = time.time() - start
        final_params = torch.cat([udm.components.params, udm.proportions.params], dim=1).detach().cpu().numpy()
        result = UDMResult(
            dataset, kernel_type, n_components,
            parameters,
            s,
            np.array(distribution_loss_series),
            np.array(component_loss_series),
            time_spent,
            final_params,
            history)
        return result
