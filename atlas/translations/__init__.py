"""Translation packages for Atlas i18n."""

from atlas.translations.en import TRANSLATIONS as EN
from atlas.translations.zh_TW import TRANSLATIONS as ZH_TW

ALL_TRANSLATIONS: dict[str, dict[str, str]] = {
    "zh-TW": ZH_TW,
    "en": EN,
}
