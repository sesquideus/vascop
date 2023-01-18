import numpy as np
import scipy as sp

from abc import ABCMeta, abstractmethod

from projections import BorovickaProjection


class Matcher(metaclass=ABCMeta):
    def __init__(self, location, time, projection_cls=BorovickaProjection):
        self.projection_cls = projection_cls
        self.update(location, time)

    @property
    @abstractmethod
    def count(self):
        pass

    def update(self, location, time):
        self.location = location
        self.time = time

    def update_sky(self):
        self.sky = self.catalogue.to_altaz_deg(self.location, self.time, masked=True)
        print(f"Updating sky: {self.sky.shape[0]} / {self.catalogue.count} valid stars")

    def avg_error(self, errors) -> float:
        if errors.size == 0:
            return np.nan
        else:
            return np.sqrt(np.sum(np.square(errors)) / self.count)

    def max_error(self, errors) -> float:
        if errors.size == 0:
            return np.nan
        else:
            return np.max(errors)

    def minimize(self, x0=(0, 0, 0, 0, 0, np.pi / 2, 0, 0, 0, 0, 0, 0), maxiter=30):
        result = sp.optimize.minimize(self.func, x0, method='Nelder-Mead',
            bounds=(
                (None, None),
                (None, None),
                (None, None),
                (None, None),
                (None, None),
                (0, None), #V
                (None, None),
                (None, None),
                (None, None),
                (None, None),
                (0, None), #epsilon
                (None, None),
            ),
            options=dict(maxiter=maxiter, disp=True),
            callback=lambda x: print(x),
        )
        return result
