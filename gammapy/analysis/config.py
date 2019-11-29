# Licensed under a 3-clause BSD style license - see LICENSE.rst
import json
import logging
from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import List
from astropy.coordinates import Angle
from astropy.time import Time
from astropy.units import Quantity
import yaml
from pydantic import BaseModel, FilePath
from pydantic.utils import deep_update
from gammapy.utils.scripts import make_path, read_yaml
from gammapy.cube import MapDatasetMaker

__all__ = ["AnalysisConfig"]

CONFIG_PATH = Path(__file__).resolve().parent / "config"
DOCS_FILE = CONFIG_PATH / "docs.yaml"
ANALYSIS_TEMPLATES = {"1d": "template-1d.yaml", "3d": "template-3d.yaml"}

log = logging.getLogger(__name__)


class AngleType(Angle):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        return Angle(v)


class EnergyType(Quantity):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        v = Quantity(v)
        if v.unit.physical_type != "energy":
            raise ValueError(f"Invalid unit for energy: {v.unit!r}")
        return v


class TimeType(Time):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        return Time(v)


class ReductionTypeEnum(str, Enum):
    spectrum = "1d"
    cube = "3d"


class FrameEnum(str, Enum):
    icrs = "icrs"
    galactic = "galactic"


class BackgroundMethodEnum(str, Enum):
    reflected = "reflected"


class MapSelectionEnum(str, Enum):
    counts = "counts"
    exposure = "exposure"
    background = "background"
    psf = "psf"
    edisp = "edisp"


class GammapyBaseConfig(BaseModel):
    class Config:
        validate_all = True
        validate_assignment = True
        extra = "forbid"
        json_encoders = {
            Angle: lambda v: f"{v.value} {v.unit}",
            Quantity: lambda v: f"{v.value} {v.unit}",
            Time: lambda v: f"{v.value}",
        }


class SkyCoordConfig(GammapyBaseConfig):
    frame: FrameEnum = None
    lon: AngleType = None
    lat: AngleType = None


class EnergyAxisConfig(GammapyBaseConfig):
    min: EnergyType = "0.1 TeV"
    max: EnergyType = "10 TeV"
    nbins: int = 30


class SpatialCircleConfig(GammapyBaseConfig):
    frame: FrameEnum = None
    lon: AngleType = None
    lat: AngleType = None
    radius: AngleType = None


class EnergyRangeConfig(GammapyBaseConfig):
    min: EnergyType = "0.1 TeV"
    max: EnergyType = "10 TeV"


class TimeRangeConfig(GammapyBaseConfig):
    start: TimeType = None
    stop: TimeType = None


class FluxPointsConfig(GammapyBaseConfig):
    energy: EnergyAxisConfig = EnergyAxisConfig()


class FitConfig(GammapyBaseConfig):
    fit_range: EnergyRangeConfig = EnergyRangeConfig()


class BackgroundConfig(GammapyBaseConfig):
    method: BackgroundMethodEnum = BackgroundMethodEnum.reflected
    exclusion: FilePath = None


class EnergyAxesConfig(GammapyBaseConfig):
    energy: EnergyAxisConfig = EnergyAxisConfig()
    energy_true: EnergyAxisConfig = EnergyAxisConfig()


class SelectionConfig(GammapyBaseConfig):
    offset_max: AngleType = "2.5 deg"


class FovConfig(GammapyBaseConfig):
    width: AngleType = "5 deg"
    height: AngleType = "5 deg"


class WcsConfig(GammapyBaseConfig):
    skydir: SkyCoordConfig = SkyCoordConfig()
    binsize: AngleType = "0.1 deg"
    fov: FovConfig = FovConfig()
    binsize_irf: AngleType = "0.1 deg"
    margin_irf: AngleType = "0.1 deg"


class GeomConfig(GammapyBaseConfig):
    wcs: WcsConfig = WcsConfig()
    selection: SelectionConfig = SelectionConfig()
    axes: EnergyAxesConfig = EnergyAxesConfig()


class DatasetsConfig(GammapyBaseConfig):
    type: ReductionTypeEnum = ReductionTypeEnum.spectrum
    stack: bool = True
    geom: GeomConfig = GeomConfig()
    map_selection: List[MapSelectionEnum] = MapDatasetMaker.available_selection
    background: BackgroundConfig = BackgroundConfig()
    on_region: SpatialCircleConfig = SpatialCircleConfig()
    containment_correction: bool = True


class ObservationsConfig(GammapyBaseConfig):
    datastore: Path = Path("$GAMMAPY_DATA/hess-dl3-dr1/")
    obs_ids: List[int] = []
    obs_file: FilePath = None
    obs_cone: SpatialCircleConfig = SpatialCircleConfig()
    obs_time: TimeRangeConfig = TimeRangeConfig()


class LogConfig(GammapyBaseConfig):
    level: str = "info"
    filename: Path = None
    filemode: str = None
    format: str = None
    datefmt: str = None


class GeneralConfig(GammapyBaseConfig):
    log: LogConfig = LogConfig()
    outdir: str = "."


class AnalysisConfig(GammapyBaseConfig):
    """Gammapy analysis configuration."""

    general: GeneralConfig = GeneralConfig()
    observations: ObservationsConfig = ObservationsConfig()
    datasets: DatasetsConfig = DatasetsConfig()
    fit: FitConfig = FitConfig()
    flux_points: FluxPointsConfig = FluxPointsConfig()

    @classmethod
    def from_template(cls, template):
        """Create from existing templates.

        Parameters
        ----------
        template : {"1d", "3d"}
            Built-in templates.

        Returns
        -------
        config : `AnalysisConfig`
            AnalysisConfig class
        """
        filename = CONFIG_PATH / ANALYSIS_TEMPLATES[template]
        return cls.read(filename)

    def __str__(self):
        """Display settings in pretty YAML format."""
        info = self.__class__.__name__ + "\n\n\t"
        data = self.to_yaml()
        data = data.replace("\n", "\n\t")
        info += data
        return info.expandtabs(tabsize=4)

    @classmethod
    def read(cls, path):
        """Reads from YAML file."""
        config = read_yaml(path)
        return AnalysisConfig(**config)

    @classmethod
    def from_yaml(cls, config_str):
        """Create from YAML string."""
        settings = yaml.safe_load(config_str)
        return AnalysisConfig(**settings)

    def write(self, path, overwrite=False):
        """Write to YAML file."""
        path = make_path(path)
        if path.exists() and not overwrite:
            raise IOError(f"File exists already: {path}")
        path.write_text(self.to_yaml())

    def to_yaml(self):
        """Convert to YAML string."""
        # Here using `dict()` instead of `json()` would be more natural.
        # We should change this once pydantic adds support for custom encoders
        # to `dict()`. See https://github.com/samuelcolvin/pydantic/issues/1043
        config = json.loads(self.json())
        return yaml.dump(config, sort_keys=False, indent=4)

    def set_logging(self):
        """Set logging config.

        Calls ``logging.basicConfig``, i.e. adjusts global logging state.
        """
        self.general.log.level = self.general.log.level.upper()
        logging.basicConfig(**self.general.log.dict())
        log.info("Setting logging config: {!r}".format(self.general.log.dict()))

    def update(self, config=None):
        """Update config with provided settings.

        Parameters
        ----------
        config : string dict or `AnalysisConfig` object
            Configuration settings provided in dict() syntax.
        """
        if isinstance(config, str):
            config = dict(yaml.safe_load(config))
        if isinstance(config, dict):
            config = AnalysisConfig(**config)
        if isinstance(config, AnalysisConfig):
            upd_config = deep_update(
                self.dict(exclude_defaults=True), config.dict(exclude_defaults=True)
            )
            return AnalysisConfig(**upd_config)

    def help(self, section=""):
        """Print template configuration settings."""
        doc = self._get_doc_sections()
        for keyword in doc.keys():
            if section == "" or section == keyword:
                print(doc[keyword])

    @staticmethod
    def _get_doc_sections():
        """Returns dict with commented docs from docs file"""
        doc = defaultdict(str)
        with open(DOCS_FILE) as f:
            for line in filter(lambda line: not line.startswith("---"), f):
                line = line.strip("\n")
                if line.startswith("# Section: "):
                    keyword = line.replace("# Section: ", "")
                doc[keyword] += line + "\n"
        return doc