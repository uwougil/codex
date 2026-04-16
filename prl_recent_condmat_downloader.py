#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import ctypes
import datetime as dt
from email.utils import parsedate_to_datetime
import os
import re
import sys
import tempfile
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode, urljoin, urlparse

from bs4 import BeautifulSoup
import requests
from scrapling.fetchers import StealthySession
import xml.etree.ElementTree as ET
import yaml


APS_BASE_URL = "https://journals.aps.org"
ACS_BASE_URL = "https://pubs.acs.org"
CONDMAT_SECTION = "condensed-matter-and-materials"
SYSTEM_PROXY_BYPASS_DOMAINS = [
    "aps.org",
    "*.aps.org",
    "acs.org",
    "*.acs.org",
    "nature.com",
    "*.nature.com",
    "springer.com",
    "*.springer.com",
    "wiley.com",
    "*.wiley.com",
    "science.org",
    "*.science.org",
    "rsc.org",
    "*.rsc.org",
    "iop.org",
    "*.iop.org",
    "aip.org",
    "*.aip.org",
    "pnas.org",
    "*.pnas.org",
    "doi.org",
    "*.doi.org",
]
CLASH_DIRECT_RULES = [
    "DOMAIN-SUFFIX,journals.aps.org,DIRECT",
    "DOMAIN-SUFFIX,link.aps.org,DIRECT",
    "DOMAIN-SUFFIX,pubs.acs.org,DIRECT",
    "DOMAIN-SUFFIX,www.nature.com,DIRECT",
    "DOMAIN-SUFFIX,link.springer.com,DIRECT",
    "DOMAIN-SUFFIX,onlinelibrary.wiley.com,DIRECT",
    "DOMAIN-SUFFIX,advanced.onlinelibrary.wiley.com,DIRECT",
    "DOMAIN-SUFFIX,www.science.org,DIRECT",
    "DOMAIN-SUFFIX,pubs.rsc.org,DIRECT",
    "DOMAIN-SUFFIX,feeds.rsc.org,DIRECT",
    "DOMAIN-SUFFIX,iopscience.iop.org,DIRECT",
    "DOMAIN-SUFFIX,pubs.aip.org,DIRECT",
    "DOMAIN-SUFFIX,www.pnas.org,DIRECT",
    "DOMAIN-SUFFIX,aps.org,DIRECT",
    "DOMAIN-SUFFIX,acs.org,DIRECT",
    "DOMAIN-SUFFIX,nature.com,DIRECT",
    "DOMAIN-SUFFIX,springer.com,DIRECT",
    "DOMAIN-SUFFIX,wiley.com,DIRECT",
    "DOMAIN-SUFFIX,science.org,DIRECT",
    "DOMAIN-SUFFIX,rsc.org,DIRECT",
    "DOMAIN-SUFFIX,iop.org,DIRECT",
    "DOMAIN-SUFFIX,aip.org,DIRECT",
    "DOMAIN-SUFFIX,pnas.org,DIRECT",
    "DOMAIN-SUFFIX,doi.org,DIRECT",
]
SECTION_OPTIONS: list[tuple[str, str]] = [
    ("editorials-essays-and-announcements", "Editorials, Essays, and Announcements"),
    ("quantum-information-science-and-technology", "Quantum Information, Science, and Technology"),
    ("cosmology-astrophysics-and-gravitation", "Cosmology, Astrophysics, and Gravitation"),
    ("particles-and-fields", "Particles and Fields"),
    ("nuclear-physics", "Nuclear Physics"),
    ("atomic-molecular-and-optical-physics", "Atomic, Molecular, and Optical Physics"),
    ("physics-of-fluids-earth-and-planetary-science-and-climate", "Physics of Fluids, Earth and Planetary Science, and Climate"),
    ("plasma-and-solar-physics-accelerators-and-beams", "Plasma and Solar Physics, Accelerators and Beams"),
    (CONDMAT_SECTION, "Condensed Matter and Materials"),
    ("statistical-physics-classical-nonlinear-and-complex-systems", "Statistical Physics; Classical, Nonlinear, and Complex Systems"),
    ("polymers-chemical-physics-soft-matter-and-biological-physics", "Polymers, Chemical Physics, Soft Matter, and Biological Physics"),
]
PUBLISHED_RE = re.compile(r"Published\s+(\d{1,2}\s+[A-Za-z]+\s*,\s*\d{4})")
ACS_PUBLISHED_RE = re.compile(r"Publication Date\s*\(Web\)\s*:\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})")
PHYSH_RE = re.compile(
    r"Physics Subject Headings\s*\(PhySH\)\s*(.+?)(?=Popular Summary|Viewpoint|Article Text|"
    r"Authorization Required|References|Published\b|Export Citation|Show Abstract|Supplemental Material|PDF\b)",
    re.IGNORECASE | re.DOTALL,
)
CONDENSED_MATTER_PHYSH_HINTS = [
    "mesoscop",
    "quantum hall",
    "quantum transport",
    "electronic structure",
    "superconduct",
    "graphene",
    "2-dimensional systems",
    "2 dimensional systems",
    "landau levels",
    "nanophotonics",
    "semiconductor",
    "thermoelectric",
    "thermoelectrics",
    "spin dynamics",
    "spin waves",
    "spintronics",
    "magnon",
    "phonon",
    "magnetoelastic",
    "magnetic anisotropy",
    "magnetism",
    "surface acoustic wave",
    "surface reconstruction",
    "surface instabilities",
    "surface physics",
    "transition metal oxide",
    "transition metal oxides",
    "ferroelectric",
    "multiferroic",
    "metamaterial",
    "metamaterials",
    "metasurface",
    "plasmon",
    "crystal",
    "materials",
    "specific heat",
    "electronic structure",
    "thermionic emission",
    "electron emission",
    "elastic deformation",
    "elastic modulus",
    "mechanical metamaterials",
    "strain",
    "rare-earth doped crystals",
]
ACS_CONDENSED_MATTER_SUBJECT_HINTS = [
    "2-dimensional materials",
    "2d materials",
    "amorphous materials",
    "batteries",
    "charge transport",
    "conductors",
    "covalent organic frameworks",
    "crystals",
    "electrodes",
    "electrolytes",
    "electronic materials",
    "electronic structure",
    "energy materials",
    "excitons",
    "ferroelectric materials",
    "graphene",
    "heterostructures",
    "ionic liquids",
    "liquids",
    "magnetic materials",
    "magnetism",
    "materials chemistry",
    "metal organic frameworks",
    "metal-organic frameworks",
    "metamaterials",
    "molecular dynamics",
    "nanocrystals",
    "nanoparticles",
    "nanosheets",
    "nanotubes",
    "nanowires",
    "optoelectronic materials",
    "perovskites",
    "phase transitions",
    "phonons",
    "photonic materials",
    "plasmonics",
    "polymers",
    "porous materials",
    "quantum dots",
    "semiconductors",
    "spintronics",
    "superconductors",
    "surface chemistry",
    "surfaces",
    "thin films",
    "topological materials",
    "viscosity",
]
ACS_CONDENSED_MATTER_TEXT_HINTS = [
    "2d material",
    "2-dimensional",
    "amorphous",
    "battery",
    "charge density wave",
    "charge transport",
    "conductivity",
    "covalent organic framework",
    "crystal",
    "electrode",
    "electrolyte",
    "electronic structure",
    "exciton",
    "ferroelectric",
    "graphene",
    "heterostructure",
    "liquid",
    "magnetic",
    "magnetism",
    "material",
    "metal-organic framework",
    "molecular dynamics",
    "nanocrystal",
    "nanoparticle",
    "nanosheet",
    "nanotube",
    "nanowire",
    "perovskite",
    "phase transition",
    "phonon",
    "photonic",
    "plasmon",
    "polymer",
    "porous",
    "quantum dot",
    "semiconductor",
    "spin",
    "superconduct",
    "surface",
    "thin film",
    "topological",
    "viscosity",
]
ACS_EXCLUSION_HINTS = [
    "antibody",
    "bio",
    "biological",
    "cancer",
    "cell",
    "dearomatization",
    "enantioselective",
    "enzyme",
    "male reproductive toxicity",
    "medicinal",
    "mice",
    "peptide",
    "protein",
    "total synthesis",
]
ACS_FRONT_MATTER_TITLE_HINTS = [
    "issue editorial masthead",
    "issue publication information",
    "masthead",
    "additions and corrections",
    "correction to",
    "publisher correction",
]
GENERIC_FRONT_MATTER_TITLE_HINTS = ACS_FRONT_MATTER_TITLE_HINTS + [
    "in this issue",
    "issue information",
    "editorial",
    "editorial overview",
    "books et al.",
    "book review",
    "erratum",
    "retraction",
    "news",
    "perspective",
    "viewpoint",
    "this week in science",
]
GENERIC_NON_RESEARCH_TYPE_HINTS = [
    "book",
    "books et al.",
    "editorial",
    "front matter",
    "issue information",
    "news",
    "perspective",
    "policy forum",
    "viewpoint",
]
GENERIC_RESEARCH_TYPE_HINTS = [
    "article",
    "communication",
    "full paper",
    "letter",
    "paper",
    "report",
    "research",
    "review",
]
GENERIC_CONDMAT_SUBJECT_HINTS = [
    "2-dimensional materials",
    "2d materials",
    "condensed-matter physics",
    "electronic materials",
    "energy materials",
    "ferroelectric materials",
    "graphene",
    "heterostructures",
    "magnetic materials",
    "magnetism",
    "materials science",
    "metamaterials",
    "nanocrystals",
    "nanoparticles",
    "nanosheets",
    "nanotubes",
    "nanowires",
    "optoelectronic materials",
    "perovskites",
    "phase transitions",
    "phonons",
    "photonic materials",
    "plasmonics",
    "porous materials",
    "quantum dots",
    "quantum materials",
    "semiconductors",
    "spintronics",
    "superconductors",
    "thin films",
    "topological materials",
]
GENERIC_CONDMAT_TEXT_HINTS = [
    "2d material",
    "2-dimensional",
    "altermagnet",
    "band structure",
    "battery",
    "charge transport",
    "colloidal nanocrystal",
    "covalent organic framework",
    "exciton",
    "ferroelectric",
    "graphene",
    "heterostructure",
    "liquid crystal",
    "magnetic",
    "magnetism",
    "metamaterial",
    "moire",
    "nanocrystal",
    "nanoparticle",
    "nanosheet",
    "nanotube",
    "nanowire",
    "optoelectronic",
    "perovskite",
    "phonon",
    "photonic",
    "plasmon",
    "quantum dot",
    "quantum material",
    "semiconductor",
    "solar cell",
    "spin current",
    "spintronics",
    "superconduct",
    "thermal conductivity",
    "thin film",
    "topological",
    "transition metal dichalcogenide",
]
PDF_FETCH_JS = r"""
async (href) => {
    const absoluteUrl = new URL(href, location.href).href;
    const response = await fetch(absoluteUrl, { credentials: "include" });
    const contentType = response.headers.get("content-type");
    const buffer = await response.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    let headHex = "";
    for (const value of bytes.slice(0, 16)) {
        headHex += value.toString(16).padStart(2, "0");
    }
    let binary = "";
    const chunkSize = 0x8000;
    for (let index = 0; index < bytes.length; index += chunkSize) {
        binary += String.fromCharCode.apply(null, bytes.subarray(index, index + chunkSize));
    }
    return {
        url: response.url,
        status: response.status,
        contentType,
        size: buffer.byteLength,
        headHex,
        b64: btoa(binary),
    };
}
"""
HTML_BATCH_FETCH_JS = r"""
async (urls) => {
    return await Promise.all(
        urls.map(async (href) => {
            const absoluteUrl = new URL(href, location.href).href;
            try {
                const response = await fetch(absoluteUrl, { credentials: "include" });
                const text = await response.text();
                return {
                    requestedUrl: absoluteUrl,
                    url: response.url,
                    status: response.status,
                    text,
                    error: "",
                };
            } catch (error) {
                return {
                    requestedUrl: absoluteUrl,
                    url: absoluteUrl,
                    status: 0,
                    text: "",
                    error: String(error),
                };
            }
        })
    );
}
"""


@dataclass(frozen=True)
class JournalSpec:
    source_key: str
    publisher: str
    short_name: str
    code: str
    classification_mode: str
    listing_mode: str = "aps_recent"
    section_slug: str | None = None
    file_tag: str | None = None
    feed_urls: tuple[str, ...] = ()
    listing_urls: tuple[str, ...] = ()

    @property
    def aps_recent_path(self) -> str:
        return f"/{self.code}/recent"

    @property
    def acs_current_toc_path(self) -> str:
        return f"/toc/{self.code}/current"

    @property
    def acs_asap_toc_path(self) -> str:
        return f"/toc/{self.code}/0/0"

    @property
    def pdf_path_fragment(self) -> str:
        if self.source_key == "acs":
            return "/doi/pdf/"
        return f"/{self.code}/pdf/"

    @property
    def normalized_file_tag(self) -> str:
        return self.file_tag or self.short_name.replace(" ", "")


TARGET_JOURNALS: tuple[JournalSpec, ...] = (
    JournalSpec(source_key="aps", publisher="APS", short_name="PRL", code="prl", classification_mode="section", listing_mode="aps_recent", section_slug=CONDMAT_SECTION, file_tag="PRL"),
    JournalSpec(source_key="aps", publisher="APS", short_name="PRX", code="prx", classification_mode="physh", listing_mode="aps_recent", file_tag="PRX"),
    JournalSpec(source_key="aps", publisher="APS", short_name="PRB", code="prb", classification_mode="journal_scope", listing_mode="aps_recent", file_tag="PRB"),
    JournalSpec(source_key="aps", publisher="APS", short_name="PRM", code="prmaterials", classification_mode="journal_scope", listing_mode="aps_recent", file_tag="PRM"),
    JournalSpec(source_key="aps", publisher="APS", short_name="PRR", code="prresearch", classification_mode="physh", listing_mode="aps_recent", file_tag="PRR"),
    JournalSpec(source_key="aps", publisher="APS", short_name="PR Applied", code="prapplied", classification_mode="physh", listing_mode="aps_recent", file_tag="PRApplied"),
    JournalSpec(source_key="acs", publisher="ACS", short_name="JACS", code="jacsat", classification_mode="acs_subjects", listing_mode="acs_toc", file_tag="JACS"),
    JournalSpec(source_key="acs", publisher="ACS", short_name="Nano Lett.", code="nalefd", classification_mode="acs_subjects", listing_mode="acs_toc", file_tag="NanoLett"),
    JournalSpec(source_key="acs", publisher="ACS", short_name="ACS Nano", code="ancac3", classification_mode="acs_subjects", listing_mode="acs_toc", file_tag="ACSNano"),
    JournalSpec(source_key="acs", publisher="ACS", short_name="JPCC", code="jpccck", classification_mode="acs_subjects", listing_mode="acs_toc", file_tag="JPCC"),
    JournalSpec(source_key="acs", publisher="ACS", short_name="JPCL", code="jpclcd", classification_mode="acs_subjects", listing_mode="acs_toc", file_tag="JPCL"),
    JournalSpec(source_key="springer_nature", publisher="Springer Nature", short_name="Nature", code="nature", classification_mode="nature_subjects", listing_mode="rss", file_tag="Nature", feed_urls=("https://www.nature.com/nature.rss",)),
    JournalSpec(source_key="springer_nature", publisher="Springer Nature", short_name="Nature Nanotechnology", code="nnano", classification_mode="nature_subjects", listing_mode="rss", file_tag="NatureNano", feed_urls=("https://www.nature.com/nnano.rss",)),
    JournalSpec(source_key="springer_nature", publisher="Springer Nature", short_name="Nature Physics", code="nphys", classification_mode="nature_subjects", listing_mode="rss", file_tag="NaturePhysics", feed_urls=("https://www.nature.com/nphys.rss",)),
    JournalSpec(source_key="springer_nature", publisher="Springer Nature", short_name="Nature Communications", code="ncomms", classification_mode="nature_subjects", listing_mode="rss", file_tag="NatureCommunications", feed_urls=("https://www.nature.com/ncomms.rss",)),
    JournalSpec(source_key="springer_nature", publisher="Springer Nature", short_name="Communications Materials", code="commsmat", classification_mode="journal_scope", listing_mode="rss", file_tag="CommunicationsMaterials", feed_urls=("https://www.nature.com/commsmat.rss",)),
    JournalSpec(source_key="springer_nature", publisher="Springer Nature", short_name="npj Computational Materials", code="npjcompumats", classification_mode="journal_scope", listing_mode="rss", file_tag="npjCompuMat", feed_urls=("https://www.nature.com/npjcompumats.rss",)),
    JournalSpec(source_key="springer_nature", publisher="Springer Nature", short_name="npj 2D Materials and Applications", code="npj2dmaterials", classification_mode="journal_scope", listing_mode="rss", file_tag="npj2DMat", feed_urls=("https://www.nature.com/npj2dmaterials.rss",)),
    JournalSpec(source_key="wiley", publisher="John Wiley", short_name="Advanced Functional Materials", code="afm", classification_mode="journal_scope", listing_mode="rss", file_tag="AFM", feed_urls=("https://onlinelibrary.wiley.com/feed/16163028/most-recent",)),
    JournalSpec(source_key="wiley", publisher="John Wiley", short_name="Advanced Energy Materials", code="aem", classification_mode="journal_scope", listing_mode="rss", file_tag="AEM", feed_urls=("https://onlinelibrary.wiley.com/feed/16146840/most-recent",)),
    JournalSpec(source_key="wiley", publisher="John Wiley", short_name="Advanced Science", code="advs", classification_mode="text_rules", listing_mode="rss", file_tag="AdvancedScience", feed_urls=("https://onlinelibrary.wiley.com/feed/21983844/most-recent",)),
    JournalSpec(source_key="wiley", publisher="John Wiley", short_name="Small", code="small", classification_mode="journal_scope", listing_mode="rss", file_tag="Small", feed_urls=("https://onlinelibrary.wiley.com/feed/16136829/most-recent",)),
    JournalSpec(source_key="aaas", publisher="AAAS", short_name="Science", code="science", classification_mode="text_rules", listing_mode="rss", file_tag="Science", feed_urls=("https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science", "https://www.science.org/action/showFeed?type=axatoc&feed=rss&jc=science")),
    JournalSpec(source_key="aaas", publisher="AAAS", short_name="Science Advances", code="sciadv", classification_mode="text_rules", listing_mode="rss", file_tag="ScienceAdvances", feed_urls=("https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciadv",)),
    JournalSpec(source_key="rsc", publisher="Royal Society of Chemistry", short_name="Materials Horizons", code="mh", classification_mode="journal_scope", listing_mode="rss", file_tag="MaterialsHorizons", feed_urls=("https://feeds.rsc.org/rss/mh",)),
    JournalSpec(source_key="rsc", publisher="Royal Society of Chemistry", short_name="J. Mater. Chem. C", code="tc", classification_mode="journal_scope", listing_mode="rss", file_tag="JMCC", feed_urls=("https://feeds.rsc.org/rss/tc",)),
    JournalSpec(source_key="rsc", publisher="Royal Society of Chemistry", short_name="PCCP", code="cp", classification_mode="text_rules", listing_mode="rss", file_tag="PCCP", feed_urls=("https://feeds.rsc.org/rss/cp",)),
    JournalSpec(source_key="iop", publisher="IOP Publishing", short_name="2D Materials", code="2053-1583", classification_mode="journal_scope", listing_mode="rss", file_tag="2DMaterials", feed_urls=("https://iopscience.iop.org/journal/rss/2053-1583",)),
    JournalSpec(source_key="aip", publisher="American Institute of Physics", short_name="Applied Physics Letters", code="apl", classification_mode="text_rules", listing_mode="rss", file_tag="APL", feed_urls=("https://pubs.aip.org/rss/site_1000017/LatestOpenIssueArticles_1000011.xml", "https://pubs.aip.org/rss/site_1000017/1000011.xml")),
    JournalSpec(source_key="nas", publisher="National Academy of Sciences", short_name="PNAS", code="pnas", classification_mode="text_rules", listing_mode="rss", file_tag="PNAS", feed_urls=("https://www.pnas.org/rss/current.xml",)),
    JournalSpec(source_key="nano_research", publisher="Tsinghua/Springer", short_name="Nano Research", code="12274", classification_mode="journal_scope", listing_mode="springer_search", file_tag="NanoResearch", listing_urls=("https://link.springer.com/search?new-search=true&query=*&search-within=Journal&sortBy=date&facet-journal-id=12274",)),
)
SOURCE_CHOICES = (
    "aps",
    "acs",
    "springer_nature",
    "wiley",
    "aaas",
    "rsc",
    "iop",
    "aip",
    "nas",
    "nano_research",
)
SOURCE_LABELS = {
    "aps": "APS",
    "acs": "ACS",
    "springer_nature": "Springer Nature",
    "wiley": "Wiley",
    "aaas": "AAAS",
    "rsc": "RSC",
    "iop": "IOP",
    "aip": "AIP",
    "nas": "PNAS",
    "nano_research": "Nano Research",
}
PROGRESS_PREFIX = "@@PROGRESS "


@dataclass(frozen=True)
class Paper:
    publisher: str
    source_key: str
    journal_short_name: str
    journal_code: str
    title: str
    abstract_url: str
    published_date: dt.date
    classification_reason: str = ""
    doi: str = ""
    abstract_text: str = ""
    article_type: str = ""
    pdf_url: str = ""

    @property
    def abstract_id(self) -> str:
        return self.doi or self.abstract_url.rstrip("/").split("/")[-1]


def _windows_internet_settings_path() -> str:
    return r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"


def refresh_windows_internet_options() -> None:
    if os.name != "nt":
        return
    internet_option_settings_changed = 39
    internet_option_refresh = 37
    ctypes.windll.wininet.InternetSetOptionW(0, internet_option_settings_changed, 0, 0)
    ctypes.windll.wininet.InternetSetOptionW(0, internet_option_refresh, 0, 0)


def ensure_windows_proxy_bypass() -> bool:
    if os.name != "nt":
        return False

    import winreg

    changed = False
    registry_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_path, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
        try:
            current_value, _ = winreg.QueryValueEx(key, "ProxyOverride")
        except FileNotFoundError:
            current_value = ""

        parts = [part.strip() for part in str(current_value).split(";") if part.strip()]
        existing = {part.lower() for part in parts}
        for domain in SYSTEM_PROXY_BYPASS_DOMAINS:
            if domain.lower() not in existing:
                parts.append(domain)
                existing.add(domain.lower())
                changed = True

        if changed:
            winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, ";".join(parts))

    if changed:
        refresh_windows_internet_options()
    return changed


def load_yaml_file(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def save_yaml_file(path: Path, data: dict | list) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)


def ensure_clash_verge_system_bypass(config_dir: Path) -> bool:
    verge_path = config_dir / "verge.yaml"
    if not verge_path.exists():
        return False

    data = load_yaml_file(verge_path)
    if not isinstance(data, dict):
        return False

    current_raw = data.get("system_proxy_bypass")
    current_parts = [part.strip() for part in str(current_raw or "").split(";") if part.strip()]
    existing = {part.lower() for part in current_parts}
    changed = False
    for domain in SYSTEM_PROXY_BYPASS_DOMAINS:
        if domain.lower() not in existing:
            current_parts.append(domain)
            existing.add(domain.lower())
            changed = True

    if changed or not data.get("use_default_bypass", True):
        data["use_default_bypass"] = True
        data["system_proxy_bypass"] = ";".join(current_parts)
        save_yaml_file(verge_path, data)
        return True
    return False


def resolve_clash_rules_file(config_dir: Path) -> Path | None:
    profiles_path = config_dir / "profiles.yaml"
    data = load_yaml_file(profiles_path)
    if not isinstance(data, dict):
        return None

    current_uid = data.get("current")
    items = data.get("items") or []
    current_remote = next((item for item in items if isinstance(item, dict) and item.get("uid") == current_uid), None)
    option = (current_remote or {}).get("option") or {}
    rules_uid = option.get("rules")
    if rules_uid:
        rules_item = next((item for item in items if isinstance(item, dict) and item.get("uid") == rules_uid), None)
        if rules_item and rules_item.get("file"):
            return config_dir / "profiles" / str(rules_item["file"])

    for item in items:
        if isinstance(item, dict) and item.get("type") == "rules" and item.get("file"):
            return config_dir / "profiles" / str(item["file"])
    return None


def clash_verge_config_dir() -> Path:
    return Path.home() / "AppData" / "Roaming" / "io.github.clash-verge-rev.clash-verge-rev"


def collect_clash_rule_strings(data: dict) -> set[str]:
    existing: set[str] = set()
    for key in ("prepend", "rules"):
        value = data.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            existing.add(str(item).strip().upper())
    return existing


def ensure_clash_direct_rules(config_dir: Path) -> bool:
    rules_path = resolve_clash_rules_file(config_dir)
    if rules_path is None or not rules_path.exists():
        return False

    data = load_yaml_file(rules_path)
    if not isinstance(data, dict):
        return False

    rules = data.get("rules")
    if rules is None:
        rules = []
        data["rules"] = rules
    if not isinstance(rules, list):
        return False

    normalized_rules: list[str] = []
    seen_rules: set[str] = set()
    for rule in rules:
        text = str(rule).strip()
        upper_text = text.upper()
        if upper_text in seen_rules:
            continue
        normalized_rules.append(text)
        seen_rules.add(upper_text)

    changed = False
    if normalized_rules != rules:
        rules[:] = normalized_rules
        changed = True

    existing = collect_clash_rule_strings(data)
    for rule in CLASH_DIRECT_RULES:
        if rule.upper() not in existing:
            rules.append(rule)
            existing.add(rule.upper())
            changed = True

    if changed:
        save_yaml_file(rules_path, data)
    return changed


def ensure_scholarly_direct_network() -> list[str]:
    if os.name != "nt":
        return []

    changed_parts: list[str] = []
    if ensure_windows_proxy_bypass():
        changed_parts.append("Windows ProxyOverride")

    clash_dir = clash_verge_config_dir()
    if clash_dir.exists():
        if ensure_clash_verge_system_bypass(clash_dir):
            changed_parts.append("Clash Verge system bypass")
        if ensure_clash_direct_rules(clash_dir):
            changed_parts.append("Clash Verge DIRECT rules")

    if changed_parts:
        log("Updated journal direct-network settings: " + ", ".join(changed_parts))
    else:
        log("Journal direct-network settings already look correct.")
    return changed_parts


def read_windows_proxy_state() -> dict[str, object]:
    if os.name != "nt":
        return {}

    import winreg

    registry_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_path, 0, winreg.KEY_READ) as key:
        def read_value(name: str, default: object) -> object:
            try:
                value, _ = winreg.QueryValueEx(key, name)
                return value
            except FileNotFoundError:
                return default

        proxy_enable = int(read_value("ProxyEnable", 0) or 0)
        proxy_server = str(read_value("ProxyServer", "") or "")
        proxy_override = str(read_value("ProxyOverride", "") or "")

    bypass_entries = {part.strip().lower() for part in proxy_override.split(";") if part.strip()}
    missing_bypass = [
        domain
        for domain in SYSTEM_PROXY_BYPASS_DOMAINS
        if domain.lower() not in bypass_entries
    ]
    return {
        "proxy_enable": proxy_enable,
        "proxy_server": proxy_server,
        "proxy_override": proxy_override,
        "missing_bypass": missing_bypass,
    }


def read_clash_direct_state(config_dir: Path) -> dict[str, object]:
    verge_path = config_dir / "verge.yaml"
    rules_path = resolve_clash_rules_file(config_dir)
    missing_bypass: list[str] = []
    missing_direct_rules: list[str] = []

    verge_data = load_yaml_file(verge_path)
    if isinstance(verge_data, dict):
        bypass_raw = str(verge_data.get("system_proxy_bypass") or "")
        existing_bypass = {part.strip().lower() for part in bypass_raw.split(";") if part.strip()}
        missing_bypass = [
            domain
            for domain in SYSTEM_PROXY_BYPASS_DOMAINS
            if domain.lower() not in existing_bypass
        ]

    if rules_path and rules_path.exists():
        rules_data = load_yaml_file(rules_path)
        if isinstance(rules_data, dict):
            existing_rules = collect_clash_rule_strings(rules_data)
            missing_direct_rules = [
                rule
                for rule in CLASH_DIRECT_RULES
                if rule.upper() not in existing_rules
            ]

    return {
        "missing_bypass": missing_bypass,
        "missing_direct_rules": missing_direct_rules,
    }


_LAST_VPN_DIAG_AT = 0.0


def is_target_journal_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(
        host.endswith(suffix)
        for suffix in (
            "aps.org",
            "acs.org",
            "nature.com",
            "springer.com",
            "wiley.com",
            "science.org",
            "rsc.org",
            "iop.org",
            "aip.org",
            "pnas.org",
            "doi.org",
        )
    )


def response_status_code(response: object) -> int | None:
    for attr in ("status", "status_code", "statusCode"):
        value = getattr(response, attr, None)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def response_body_bytes(response: object) -> bytes:
    body = getattr(response, "body", b"")
    if isinstance(body, bytes):
        return body
    if body is None:
        return b""
    return str(body).encode("utf-8", "ignore")


def looks_like_scholarly_challenge(response: object) -> str | None:
    status = response_status_code(response)
    if status in {403, 429, 503}:
        return f"HTTP {status}"

    body_text = response_body_bytes(response).decode("utf-8", "ignore").lower()
    markers = [
        "just a moment",
        "enable javascript and cookies to continue",
        "attention required",
        "access denied",
    ]
    for marker in markers:
        if marker in body_text:
            return f"challenge marker '{marker}'"
    return None


def diagnose_possible_vpn_issue(url: str, reason: str) -> None:
    if not is_target_journal_url(url):
        return

    global _LAST_VPN_DIAG_AT
    now = time.time()
    if now - _LAST_VPN_DIAG_AT < 8:
        return
    _LAST_VPN_DIAG_AT = now

    log(f"Journal page access failed ({reason}). Checking whether VPN/proxy routing is the cause...")

    notes: list[str] = []
    proxy_state = read_windows_proxy_state()
    if proxy_state:
        missing_bypass = proxy_state.get("missing_bypass") or []
        if missing_bypass:
            notes.append("Windows ProxyOverride is missing scholarly-domain bypass entries")
        elif proxy_state.get("proxy_enable"):
            notes.append("Windows system proxy is still enabled; scholarly-domain bypass exists, but a stale browser route may still interfere")

    clash_dir = clash_verge_config_dir()
    if clash_dir.exists():
        clash_state = read_clash_direct_state(clash_dir)
        if clash_state.get("missing_bypass"):
            notes.append("Clash Verge system_proxy_bypass is missing scholarly domains")
        if clash_state.get("missing_direct_rules"):
            notes.append("Clash Verge DIRECT rules for scholarly domains are incomplete")

    if notes:
        log("Possible VPN/proxy cause: " + "; ".join(notes))
    else:
        log("Proxy bypass entries already look present. The failure may still come from a stale browser session or DNS route established before the bypass took effect.")

    changed_parts = ensure_scholarly_direct_network()
    if changed_parts:
        log("Applied journal direct-network repair and will retry the request.")
    else:
        log("No routing change was needed. Retrying with the current network/session state.")


def parse_args() -> argparse.Namespace:
    default_profile = Path(tempfile.gettempdir()) / "prl_scrapling_profile"

    parser = argparse.ArgumentParser(
        description=(
            "Download recent condensed-matter PDFs across selected publisher groups "
            "by combining official journal sections, RSS feeds, subject taxonomies, "
            "and rule-based title/abstract filtering."
        )
    )
    parser.add_argument(
        "--days",
        type=int,
        default=3,
        help="Recent day window, inclusive of today. Example: 3 means today and the prior 2 days.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory where PDFs will be saved.",
    )
    parser.add_argument(
        "--user-data-dir",
        type=Path,
        default=default_profile,
        help=(
            "Persistent browser profile directory. Reusing it helps keep Cloudflare "
            "and institution session state across runs."
        ),
    )
    parser.add_argument(
        "--today",
        type=str,
        default=None,
        help="Override today's date in YYYY-MM-DD format for reproducible testing.",
    )
    parser.add_argument(
        "--section",
        type=str,
        default=CONDMAT_SECTION,
        help=(
            "PRL-only toc_section slug. Default is condensed-matter-and-materials. "
            "Other journals use journal scope, APS PhySH, site subject tags, or text rules."
        ),
    )
    parser.add_argument(
        "--sources",
        type=str,
        default="aps,acs",
        help=(
            "Comma-separated sources to scan. Supported values: "
            + ", ".join(SOURCE_CHOICES)
            + ". Default: aps,acs"
        ),
    )
    parser.add_argument(
        "--parallel-sites",
        action="store_true",
        help=(
            "Enable parallel search. With multiple sources it parallelizes publisher groups at the site level; "
            "with one source it parallelizes journals for that source using separate browser profiles."
        ),
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the browser headlessly. If Cloudflare-like verification fails, the script retries in headed mode.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite PDFs that already exist.",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="List matching papers without downloading PDFs.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=20,
        help="Safety limit on how many recent-result pages to scan.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=4,
        help="Retries for each page fetch and each PDF download.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=120_000,
        help="Browser operation timeout in milliseconds.",
    )
    return parser.parse_args()


def log(message: str) -> None:
    now = dt.datetime.now().strftime("%H:%M:%S")
    print(safe_console_text(f"[{now}] {message}"), flush=True)


def fail(message: str) -> None:
    print(safe_console_text(f"ERROR: {message}", stream=sys.stderr), file=sys.stderr, flush=True)
    raise SystemExit(1)


def normalize_space(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def safe_console_text(text: str, *, stream=None) -> str:
    target = stream or sys.stdout
    encoding = getattr(target, "encoding", None) or "utf-8"
    return str(text).encode(encoding, errors="replace").decode(encoding, errors="replace")


def emit_progress(stage: str, current: int, total: int, label: str, *, source: str = "") -> None:
    payload = {
        "stage": stage,
        "current": current,
        "total": total,
        "label": label,
        "source": source,
    }
    print(PROGRESS_PREFIX + json.dumps(payload, ensure_ascii=False), flush=True)


def parse_sources(value: str) -> list[str]:
    raw_items = [part.strip().lower() for part in str(value or "").split(",") if part.strip()]
    if not raw_items:
        return list(SOURCE_CHOICES)

    unique: list[str] = []
    for item in raw_items:
        if item not in SOURCE_CHOICES:
            fail(f"Unsupported source '{item}'. Supported values: {', '.join(SOURCE_CHOICES)}.")
        if item not in unique:
            unique.append(item)
    return unique


def journals_for_sources(sources: Iterable[str]) -> list[JournalSpec]:
    selected = {source.lower() for source in sources}
    return [journal for journal in TARGET_JOURNALS if journal.source_key.lower() in selected]


def slugify_filename(title: str, abstract_id: str) -> str:
    ascii_title = (
        unicodedata.normalize("NFKD", title)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    ascii_title = normalize_space(ascii_title)
    ascii_title = re.sub(r'[<>:"/\\|?*]', "", ascii_title)
    ascii_title = ascii_title.strip(" .")
    if not ascii_title:
        ascii_title = abstract_id
    return ascii_title[:180]


def parse_aps_date(text: str) -> dt.date:
    return dt.datetime.strptime(text, "%d %B, %Y").date()


def parse_acs_date(text: str) -> dt.date:
    return dt.datetime.strptime(text, "%B %d, %Y").date()


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1].split(":", 1)[-1].lower()


def xml_child_text(item: ET.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in list(item):
        if local_name(child.tag) in wanted and child.text:
            text = normalize_space(child.text)
            if text:
                return text
    return ""


def xml_child_texts(item: ET.Element, *names: str) -> list[str]:
    wanted = {name.lower() for name in names}
    values: list[str] = []
    for child in list(item):
        if local_name(child.tag) in wanted and child.text:
            text = normalize_space(child.text)
            if text:
                values.append(text)
    return values


def strip_html_to_text(fragment: str) -> str:
    soup = BeautifulSoup(fragment or "", "html.parser")
    return normalize_space(soup.get_text(" ", strip=True))


def extract_doi_from_text(text: str) -> str:
    match = re.search(r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)", text or "", flags=re.IGNORECASE)
    return match.group(1).rstrip(").,; ") if match else ""


def parse_feed_date(value: str) -> dt.date | None:
    cleaned = normalize_space(value)
    if not cleaned:
        return None

    for parser in (
        lambda text: dt.datetime.fromisoformat(text.replace("Z", "+00:00")),
        parsedate_to_datetime,
    ):
        try:
            parsed = parser(cleaned)
            if isinstance(parsed, dt.date) and not isinstance(parsed, dt.datetime):
                return parsed
            return parsed.date()
        except Exception:
            continue

    for fmt in ("%Y-%m-%d", "%d %B %Y", "%B %d, %Y"):
        try:
            return dt.datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def request_text_with_retry(url: str, *, retries: int, timeout_ms: int) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    last_error: Exception | None = None
    timeout_seconds = max(10, int(timeout_ms / 1000))
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=timeout_seconds)
            response.raise_for_status()
            return response.text
        except Exception as error:
            last_error = error
            if attempt == retries:
                break
            log(f"Retrying plain HTTP fetch for {url} after attempt {attempt}/{retries} failed: {error}")
            time.sleep(min(attempt, 3))
    if last_error is None:
        raise RuntimeError(f"Unknown feed fetch failure for {url}")
    raise last_error


def is_generic_front_matter(title: str, article_type: str = "") -> bool:
    lowered_title = normalize_space(title).lower()
    lowered_type = normalize_space(article_type).lower()
    if any(hint in lowered_title for hint in GENERIC_FRONT_MATTER_TITLE_HINTS):
        return True
    if lowered_type and any(hint in lowered_type for hint in GENERIC_NON_RESEARCH_TYPE_HINTS):
        return True
    return False


def looks_like_research_output(article_type: str) -> bool:
    lowered = normalize_space(article_type).lower()
    if not lowered:
        return True
    if any(hint in lowered for hint in GENERIC_NON_RESEARCH_TYPE_HINTS):
        return False
    return any(hint in lowered for hint in GENERIC_RESEARCH_TYPE_HINTS)


def match_generic_condensed_matter(subjects: list[str], text: str) -> str | None:
    normalized_subjects = [normalize_space(subject).lower() for subject in subjects]
    subject_matches: list[str] = []
    for hint in GENERIC_CONDMAT_SUBJECT_HINTS:
        for subject in normalized_subjects:
            if hint in subject and subject not in subject_matches:
                subject_matches.append(subject)

    if subject_matches:
        return "Subject tags matched: " + ", ".join(subject_matches[:4])

    lowered_text = normalize_space(text).lower()
    text_matches: list[str] = []
    for hint in GENERIC_CONDMAT_TEXT_HINTS:
        if hint in lowered_text and hint not in text_matches:
            text_matches.append(hint)

    exclusion_hits = [hint for hint in ACS_EXCLUSION_HINTS if hint in lowered_text]
    if text_matches and len(text_matches) >= max(1, len(exclusion_hits) + 1):
        return "Title/abstract matched: " + ", ".join(text_matches[:4])
    return None


def is_nature_news_feature_url(url: str) -> bool:
    lowered_url = normalize_space(url).lower()
    return "/articles/d41586-" in lowered_url


def parse_rss_recent_papers(
    xml_text: str,
    *,
    cutoff_date: dt.date,
    journal: JournalSpec,
) -> list[Paper]:
    root = ET.fromstring(xml_text)
    papers: list[Paper] = []

    items = [node for node in root.findall(".//*") if local_name(node.tag) == "item"]
    for item in items:
        title = xml_child_text(item, "title")
        link = xml_child_text(item, "link")
        date_text = (
            xml_child_text(item, "date")
            or xml_child_text(item, "pubDate")
            or xml_child_text(item, "updated")
            or xml_child_text(item, "coverDate")
            or xml_child_text(item, "coverDisplayDate")
        )
        published_date = parse_feed_date(date_text)
        if not title or not link or published_date is None or published_date < cutoff_date:
            continue

        description_html = (
            xml_child_text(item, "description")
            or xml_child_text(item, "encoded")
        )
        description_text = strip_html_to_text(description_html)
        article_type = (
            xml_child_text(item, "type")
            or xml_child_text(item, "category")
        )
        doi = (
            xml_child_text(item, "doi")
            or extract_doi_from_text(xml_child_text(item, "identifier"))
            or extract_doi_from_text(xml_child_text(item, "guid"))
            or extract_doi_from_text(link)
        )
        pdf_url = xml_child_text(item, "pdf")
        papers.append(
            Paper(
                publisher=journal.publisher,
                source_key=journal.source_key,
                journal_short_name=journal.short_name,
                journal_code=journal.code,
                title=title,
                abstract_url=link,
                published_date=published_date,
                doi=doi,
                abstract_text=description_text,
                article_type=article_type,
                pdf_url=pdf_url,
            )
        )

    return dedupe_papers(papers)


def collect_rss_journal_papers(
    *,
    journal: JournalSpec,
    cutoff_date: dt.date,
    retries: int,
    timeout_ms: int,
) -> list[Paper]:
    papers: list[Paper] = []
    for url in journal.feed_urls:
        log(f"Scanning {journal.short_name} feed: {url}")
        xml_text = request_text_with_retry(url, retries=retries, timeout_ms=timeout_ms)
        feed_papers = parse_rss_recent_papers(xml_text, cutoff_date=cutoff_date, journal=journal)
        log(f"{journal.short_name} feed yielded {len(feed_papers)} recent candidates.")
        papers.extend(feed_papers)
    return dedupe_papers(papers)


SPRINGER_SEARCH_DATE_RE = re.compile(r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})")


def parse_springer_search_papers(
    page_text: str,
    *,
    cutoff_date: dt.date,
    journal: JournalSpec,
) -> list[Paper]:
    soup = BeautifulSoup(page_text, "html.parser")
    papers: list[Paper] = []
    for anchor in soup.select('a[href*="/article/"]'):
        title = normalize_space(anchor.get_text(" ", strip=True))
        if not title:
            continue
        box = anchor.find_parent("li") or anchor.find_parent("article") or anchor.find_parent("div")
        box_text = normalize_space(box.get_text(" ", strip=True) if box else "")
        date_match = SPRINGER_SEARCH_DATE_RE.search(box_text)
        if date_match is None:
            continue
        published_date = dt.datetime.strptime(date_match.group(1), "%d %B %Y").date()
        if published_date < cutoff_date:
            continue
        papers.append(
            Paper(
                publisher=journal.publisher,
                source_key=journal.source_key,
                journal_short_name=journal.short_name,
                journal_code=journal.code,
                title=title,
                abstract_url=urljoin("https://link.springer.com", anchor.get("href") or ""),
                published_date=published_date,
                abstract_text=box_text,
            )
        )
    return dedupe_papers(papers)


def collect_springer_search_journal_papers(
    *,
    journal: JournalSpec,
    cutoff_date: dt.date,
    retries: int,
    timeout_ms: int,
) -> list[Paper]:
    papers: list[Paper] = []
    for url in journal.listing_urls:
        log(f"Scanning {journal.short_name} search page: {url}")
        html_text = request_text_with_retry(url, retries=retries, timeout_ms=timeout_ms)
        parsed = parse_springer_search_papers(html_text, cutoff_date=cutoff_date, journal=journal)
        log(f"{journal.short_name} search page yielded {len(parsed)} recent candidates.")
        papers.extend(parsed)
    return dedupe_papers(papers)


def extract_nature_subjects(page_text: str) -> list[str]:
    soup = BeautifulSoup(page_text, "html.parser")
    subjects: list[str] = []
    for anchor in soup.select('.c-article-subject-list a[href*="/subjects/"], a[href*="/subjects/"]'):
        subject = normalize_space(anchor.get_text(" ", strip=True))
        if subject and subject not in subjects:
            subjects.append(subject)
    return subjects


def extract_generic_meta_description(page_text: str) -> str:
    soup = BeautifulSoup(page_text, "html.parser")
    for selector in (
        'meta[name="dc.Description"]',
        'meta[name="description"]',
        'meta[property="og:description"]',
    ):
        node = soup.select_one(selector)
        if node and node.get("content"):
            return normalize_space(node.get("content"))
    return ""


def filter_papers_by_nature_subjects(
    *,
    journal: JournalSpec,
    candidates: list[Paper],
    retries: int,
    timeout_ms: int,
) -> list[Paper]:
    filtered: list[Paper] = []
    for index, paper in enumerate(candidates, start=1):
        if is_generic_front_matter(paper.title, paper.article_type):
            log(f"Skipping front matter for {journal.short_name}: {paper.title}")
            continue
        if is_nature_news_feature_url(paper.abstract_url):
            log(f"Skipping Nature news/feature item for {journal.short_name}: {paper.title}")
            continue
        if not looks_like_research_output(paper.article_type):
            log(f"Skipping non-research Nature item for {journal.short_name}: {paper.title}")
            continue
        try:
            page_text = request_text_with_retry(paper.abstract_url, retries=retries, timeout_ms=timeout_ms)
        except Exception as error:
            log(f"Skipping '{paper.title}' after Nature article-page fetch failed: {error}")
            continue
        subjects = extract_nature_subjects(page_text)
        description = extract_generic_meta_description(page_text)
        classification_reason = match_generic_condensed_matter(subjects, " ".join([paper.title, paper.abstract_text, description]))
        if classification_reason:
            filtered.append(replace(paper, classification_reason=classification_reason, abstract_text=description or paper.abstract_text))
            log(f"Accepted {journal.short_name} candidate {index}/{len(candidates)} via Nature subjects: {paper.title}")
        else:
            log(f"Filtered out {journal.short_name} candidate by Nature subject/text rules: {paper.title}")
    return filtered


def filter_papers_by_text_rules(
    *,
    journal: JournalSpec,
    candidates: list[Paper],
) -> list[Paper]:
    filtered: list[Paper] = []
    for paper in candidates:
        if is_generic_front_matter(paper.title, paper.article_type):
            log(f"Skipping front matter for {journal.short_name}: {paper.title}")
            continue
        if not looks_like_research_output(paper.article_type):
            log(f"Skipping non-research item for {journal.short_name}: {paper.title}")
            continue
        classification_reason = match_generic_condensed_matter([], " ".join([paper.title, paper.abstract_text, paper.article_type]))
        if classification_reason:
            filtered.append(replace(paper, classification_reason=classification_reason))
    return filtered


def build_aps_recent_url(journal: JournalSpec, page: int, *, prl_section_slug: str) -> str:
    params: list[tuple[str, str]] = []
    if journal.classification_mode == "section":
        params.append(("toc_section[]", prl_section_slug or (journal.section_slug or CONDMAT_SECTION)))
    if page > 1:
        params.append(("page", str(page)))
    query = urlencode(params)
    base = f"{APS_BASE_URL}{journal.aps_recent_path}"
    return f"{base}?{query}" if query else base


def build_acs_listing_urls(journal: JournalSpec) -> list[str]:
    return [
        f"{ACS_BASE_URL}{journal.acs_current_toc_path}",
        f"{ACS_BASE_URL}{journal.acs_asap_toc_path}",
    ]


def extract_physh_text(page_body: bytes) -> str:
    soup = BeautifulSoup(page_body, "html.parser")
    text = "\n".join(soup.stripped_strings)
    match = PHYSH_RE.search(text)
    if match:
        return normalize_space(match.group(1))

    lower_text = text.lower()
    label = "physics subject headings (physh)"
    start = lower_text.find(label)
    if start == -1:
        return ""

    tail = text[start + len(label):]
    stop_match = re.search(
        r"\b(Popular Summary|Viewpoint|Article Text|Authorization Required|References|"
        r"Published|Export Citation|Show Abstract|Supplemental Material|PDF)\b",
        tail,
        flags=re.IGNORECASE,
    )
    if stop_match:
        tail = tail[:stop_match.start()]
    return normalize_space(tail)


def match_condensed_matter_physh(physh_text: str) -> str | None:
    lowered = physh_text.lower()
    matches: list[str] = []
    for hint in CONDENSED_MATTER_PHYSH_HINTS:
        if hint in lowered and hint not in matches:
            matches.append(hint)

    if not matches:
        return None
    return "APS PhySH matched: " + ", ".join(matches[:4])


def extract_acs_subjects(page_body: bytes) -> list[str]:
    soup = BeautifulSoup(page_body, "html.parser")
    section = soup.select_one(".article__tags--subjects")
    if section is None:
        return []
    subjects: list[str] = []
    for anchor in section.select("a.article__tags__link"):
        subject = normalize_space(anchor.get_text(" ", strip=True))
        if subject and subject not in subjects:
            subjects.append(subject)
    return subjects


def extract_acs_meta_description(page_body: bytes) -> str:
    soup = BeautifulSoup(page_body, "html.parser")
    for key, value in (("name", "dc.Description"), ("name", "Description"), ("property", "og:description")):
        meta = soup.find("meta", attrs={key: value})
        if meta and meta.get("content"):
            return normalize_space(str(meta["content"]))
    abstract_node = soup.select_one(".hlFld-Abstract, .article_abstract-content, p.articleBody_abstractText")
    if abstract_node is None:
        return ""
    return normalize_space(abstract_node.get_text(" ", strip=True))


def extract_acs_card_abstract(card) -> str:
    abstract_node = card.select_one(".toc-item__abstract, .hlFld-Abstract")
    if abstract_node is None:
        return ""
    return normalize_space(abstract_node.get_text(" ", strip=True))


def match_acs_condensed_matter(subjects: list[str], text: str) -> str | None:
    normalized_subjects = [normalize_space(subject).lower() for subject in subjects]
    subject_matches: list[str] = []
    for hint in ACS_CONDENSED_MATTER_SUBJECT_HINTS:
        for subject in normalized_subjects:
            if hint in subject and subject not in subject_matches:
                subject_matches.append(subject)

    if subject_matches:
        return "ACS Subjects matched: " + ", ".join(subject_matches[:4])

    lowered_text = normalize_space(text).lower()
    text_matches: list[str] = []
    for hint in ACS_CONDENSED_MATTER_TEXT_HINTS:
        if hint in lowered_text and hint not in text_matches:
            text_matches.append(hint)

    exclusion_hits = [hint for hint in ACS_EXCLUSION_HINTS if hint in lowered_text]
    if text_matches and len(text_matches) >= max(1, len(exclusion_hits) + 1):
        return "ACS title/abstract matched: " + ", ".join(text_matches[:4])
    return None


def is_acs_front_matter_title(title: str) -> bool:
    lowered_title = normalize_space(title).lower()
    return any(hint in lowered_title for hint in ACS_FRONT_MATTER_TITLE_HINTS)


def parse_aps_recent_papers(page_body: bytes, cutoff_date: dt.date, journal: JournalSpec) -> tuple[list[Paper], bool]:
    soup = BeautifulSoup(page_body, "html.parser")
    papers: list[Paper] = []

    for card in soup.select("div.browse-result-card"):
        title_anchor = card.select_one('h4.title a[href*="/abstract/"]')
        if title_anchor is None or not title_anchor.get("href"):
            continue

        title = normalize_space(title_anchor.get_text(" ", strip=True))
        abstract_url = urljoin(APS_BASE_URL, title_anchor["href"])

        published_date: dt.date | None = None
        for paragraph in card.select("section.description-container p"):
            match = PUBLISHED_RE.search(normalize_space(paragraph.get_text(" ", strip=True)))
            if match:
                published_date = parse_aps_date(match.group(1))
                break

        if published_date is None:
            continue
        if published_date < cutoff_date:
            return papers, True

        if journal.classification_mode == "section":
            reason = f"{journal.short_name} official recent section: Condensed Matter and Materials"
        elif journal.classification_mode == "journal_scope":
            reason = f"{journal.short_name} journal scope is already condensed matter/materials"
        else:
            reason = ""

        papers.append(
            Paper(
                publisher=journal.publisher,
                source_key=journal.source_key,
                journal_short_name=journal.short_name,
                journal_code=journal.code,
                title=title,
                abstract_url=abstract_url,
                published_date=published_date,
                classification_reason=reason,
            )
        )

    return papers, False


def parse_acs_listing_papers(page_body: bytes, cutoff_date: dt.date, journal: JournalSpec) -> tuple[list[Paper], bool]:
    soup = BeautifulSoup(page_body, "html.parser")
    papers: list[Paper] = []

    for card in soup.select("div.issue-item, li.issue-item"):
        doi_input = card.select_one('input[name="doi"]')
        doi = normalize_space(doi_input.get("value")) if doi_input else ""
        if not doi:
            continue

        title_anchor = card.select_one("h3.issue-item_title a[href], h5.issue-item_title a[href], .issue-item_title a[href]")
        if title_anchor is None or not title_anchor.get("href"):
            continue

        title = normalize_space(title_anchor.get_text(" ", strip=True))
        if not title:
            continue

        card_text = normalize_space(card.get_text(" ", strip=True))
        match = ACS_PUBLISHED_RE.search(card_text)
        if match is None:
            continue

        published_date = parse_acs_date(match.group(1))
        if published_date < cutoff_date:
            continue

        abstract_text = extract_acs_card_abstract(card)
        papers.append(
            Paper(
                publisher=journal.publisher,
                source_key=journal.source_key,
                journal_short_name=journal.short_name,
                journal_code=journal.code,
                title=title,
                abstract_url=urljoin(ACS_BASE_URL, title_anchor["href"]),
                published_date=published_date,
                doi=doi,
                abstract_text=abstract_text,
            )
        )

    return papers, False


def fetch_with_retry(
    session: StealthySession,
    url: str,
    *,
    retries: int,
    timeout_ms: int,
    page_action=None,
) -> object:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = session.fetch(
                url,
                timeout=timeout_ms,
                wait=500,
                page_action=page_action,
            )
            challenge_reason = looks_like_scholarly_challenge(response)
            if challenge_reason:
                diagnose_possible_vpn_issue(url, challenge_reason)
                last_error = RuntimeError(f"Journal site returned a challenge-like response: {challenge_reason}")
                if attempt == retries:
                    break
                log(f"Retrying {url} after attempt {attempt}/{retries} returned {challenge_reason}.")
                time.sleep(min(attempt, 3))
                continue
            return response
        except Exception as error:  # pragma: no cover - network and browser failures are environment-specific
            last_error = error
            diagnose_possible_vpn_issue(url, str(error))
            if attempt == retries:
                break
            log(f"Retrying {url} after attempt {attempt}/{retries} failed: {error}")
            time.sleep(min(attempt, 3))
    if last_error is None:
        raise RuntimeError(f"Unknown fetch failure for {url}")
    raise last_error


def dedupe_papers(papers: Iterable[Paper]) -> list[Paper]:
    unique: dict[str, Paper] = {}
    for paper in papers:
        key = paper.doi or paper.abstract_url
        unique[key] = paper
    return list(unique.values())


def filter_papers_by_physh(
    session: StealthySession,
    *,
    journal: JournalSpec,
    candidates: list[Paper],
    retries: int,
    timeout_ms: int,
) -> list[Paper]:
    filtered: list[Paper] = []
    for index, paper in enumerate(candidates, start=1):
        log(f"Checking APS PhySH for {journal.short_name} candidate {index}/{len(candidates)}: {paper.title}")
        try:
            response = fetch_with_retry(
                session,
                paper.abstract_url,
                retries=retries,
                timeout_ms=timeout_ms,
            )
        except Exception as error:
            log(f"Skipping '{paper.title}' after article-page fetch failed: {error}")
            continue

        physh_text = extract_physh_text(response_body_bytes(response))
        classification_reason = match_condensed_matter_physh(physh_text)
        if classification_reason:
            filtered.append(replace(paper, classification_reason=classification_reason))
            log(f"Accepted {journal.short_name} paper via PhySH: {paper.title}")
            continue

        if physh_text:
            log(f"Filtered out {journal.short_name} candidate by PhySH: {paper.title}")
        else:
            log(f"No APS PhySH was found on the article page, skipping: {paper.title}")
    return filtered


def filter_papers_by_acs_subjects(
    session: StealthySession,
    *,
    journal: JournalSpec,
    candidates: list[Paper],
    retries: int,
    timeout_ms: int,
) -> list[Paper]:
    filtered: list[Paper] = []
    pending = [paper for paper in candidates if not is_acs_front_matter_title(paper.title)]
    batch_bodies: dict[str, bytes] = {}
    acs_timeout_ms = min(timeout_ms, 35_000)

    if pending:
        seed_url = build_acs_listing_urls(journal)[0]
        batch_size = 6
        for batch_start in range(0, len(pending), batch_size):
            batch = pending[batch_start:batch_start + batch_size]
            state: dict[str, object] = {"items": []}

            def page_action(page) -> None:
                state["items"] = page.evaluate(HTML_BATCH_FETCH_JS, [paper.abstract_url for paper in batch])

            try:
                fetch_with_retry(
                    session,
                    seed_url,
                    retries=retries,
                    timeout_ms=acs_timeout_ms,
                    page_action=page_action,
                )
            except Exception as error:
                log(
                    f"ACS batch article fetch failed for {journal.short_name} "
                    f"candidates {batch_start + 1}-{batch_start + len(batch)}: {error}"
                )
                continue

            for item in list(state.get("items") or []):
                if not isinstance(item, dict):
                    continue
                requested_url = str(item.get("requestedUrl") or "")
                status = int(item.get("status") or 0)
                body_text = str(item.get("text") or "")
                error_text = normalize_space(str(item.get("error") or ""))
                if error_text:
                    log(f"ACS in-page fetch failed for {requested_url}: {error_text}")
                    continue
                fake_response = type("AcsBatchResponse", (), {"status": status, "body": body_text.encode("utf-8", "ignore")})()
                challenge_reason = looks_like_scholarly_challenge(fake_response)
                if challenge_reason:
                    log(f"ACS in-page fetch returned a challenge-like payload for {requested_url}: {challenge_reason}")
                    continue
                batch_bodies[requested_url] = body_text.encode("utf-8", "ignore")

    for index, paper in enumerate(candidates, start=1):
        log(f"Checking ACS Subjects for {journal.short_name} candidate {index}/{len(candidates)}: {paper.title}")
        if is_acs_front_matter_title(paper.title):
            log(f"Skipping ACS front matter candidate: {paper.title}")
            continue

        page_body = batch_bodies.get(paper.abstract_url)
        if page_body is None:
            try:
                response = fetch_with_retry(
                    session,
                    paper.abstract_url,
                    retries=retries,
                    timeout_ms=acs_timeout_ms,
                )
            except Exception as error:
                log(f"Skipping '{paper.title}' after article-page fetch failed: {error}")
                continue
            page_body = response_body_bytes(response)

        subjects = extract_acs_subjects(page_body)
        description = extract_acs_meta_description(page_body)
        combined_text = " ".join(
            piece for piece in [paper.title, paper.abstract_text, description] if piece
        )
        classification_reason = match_acs_condensed_matter(subjects, combined_text)
        if classification_reason:
            filtered.append(replace(paper, classification_reason=classification_reason, abstract_text=description or paper.abstract_text))
            log(f"Accepted {journal.short_name} paper via ACS classification: {paper.title}")
            continue

        if subjects:
            log(f"Filtered out {journal.short_name} candidate by ACS Subjects: {paper.title}")
        else:
            log(f"No ACS Subjects were found on the article page, skipping: {paper.title}")
    return filtered


def collect_aps_journal_papers(
    session: StealthySession,
    *,
    journal: JournalSpec,
    section_slug: str,
    cutoff_date: dt.date,
    max_pages: int,
    retries: int,
    timeout_ms: int,
) -> list[Paper]:
    papers: list[Paper] = []
    for page_number in range(1, max_pages + 1):
        url = build_aps_recent_url(journal, page_number, prl_section_slug=section_slug)
        log(f"Scanning {journal.short_name} recent page {page_number}: {url}")
        response = fetch_with_retry(session, url, retries=retries, timeout_ms=timeout_ms)
        page_papers, reached_older_items = parse_aps_recent_papers(
            response_body_bytes(response),
            cutoff_date,
            journal,
        )
        log(f"{journal.short_name} page {page_number} yielded {len(page_papers)} recent candidates.")
        papers.extend(page_papers)
        if reached_older_items or not page_papers:
            break
    return dedupe_papers(papers)


def collect_acs_journal_papers(
    session: StealthySession,
    *,
    journal: JournalSpec,
    cutoff_date: dt.date,
    retries: int,
    timeout_ms: int,
) -> list[Paper]:
    papers: list[Paper] = []
    acs_timeout_ms = min(timeout_ms, 35_000)
    for label, url in (("current", build_acs_listing_urls(journal)[0]), ("asap", build_acs_listing_urls(journal)[1])):
        log(f"Scanning {journal.short_name} {label} listing: {url}")
        response = fetch_with_retry(session, url, retries=retries, timeout_ms=acs_timeout_ms)
        page_papers, _ = parse_acs_listing_papers(
            response_body_bytes(response),
            cutoff_date,
            journal,
        )
        log(f"{journal.short_name} {label} listing yielded {len(page_papers)} recent candidates.")
        papers.extend(page_papers)
    return dedupe_papers(papers)


def collect_recent_papers(
    session: StealthySession,
    *,
    journals: Iterable[JournalSpec] | None = None,
    section_slug: str,
    cutoff_date: dt.date,
    max_pages: int,
    retries: int,
    timeout_ms: int,
    source_label: str = "",
) -> list[Paper]:
    papers: list[Paper] = []
    journal_list = list(journals or TARGET_JOURNALS)
    total_journals = len(journal_list)

    emit_progress("journals", 0, max(total_journals, 1), f"准备扫描 {total_journals} 本期刊", source=source_label)
    for journal_index, journal in enumerate(journal_list, start=1):
        if journal.listing_mode == "acs_toc":
            journal_candidates = collect_acs_journal_papers(
                session,
                journal=journal,
                cutoff_date=cutoff_date,
                retries=retries,
                timeout_ms=timeout_ms,
            )
        elif journal.listing_mode == "aps_recent":
            journal_candidates = collect_aps_journal_papers(
                session,
                journal=journal,
                section_slug=section_slug,
                cutoff_date=cutoff_date,
                max_pages=max_pages,
                retries=retries,
                timeout_ms=timeout_ms,
            )
        elif journal.listing_mode == "rss":
            journal_candidates = collect_rss_journal_papers(
                journal=journal,
                cutoff_date=cutoff_date,
                retries=retries,
                timeout_ms=timeout_ms,
            )
        elif journal.listing_mode == "springer_search":
            journal_candidates = collect_springer_search_journal_papers(
                journal=journal,
                cutoff_date=cutoff_date,
                retries=retries,
                timeout_ms=timeout_ms,
            )
        else:
            raise RuntimeError(f"Unsupported listing mode '{journal.listing_mode}' for {journal.short_name}")

        if journal.classification_mode == "physh":
            log(f"{journal.short_name} needs APS PhySH filtering for {len(journal_candidates)} candidates.")
            journal_candidates = filter_papers_by_physh(
                session,
                journal=journal,
                candidates=journal_candidates,
                retries=retries,
                timeout_ms=timeout_ms,
            )
            log(f"{journal.short_name} kept {len(journal_candidates)} condensed-matter papers after PhySH filtering.")
        elif journal.classification_mode == "acs_subjects":
            log(f"{journal.short_name} needs ACS Subjects filtering for {len(journal_candidates)} candidates.")
            journal_candidates = filter_papers_by_acs_subjects(
                session,
                journal=journal,
                candidates=journal_candidates,
                retries=retries,
                timeout_ms=timeout_ms,
            )
            log(f"{journal.short_name} kept {len(journal_candidates)} condensed-matter papers after ACS filtering.")
        elif journal.classification_mode == "nature_subjects":
            log(f"{journal.short_name} needs Nature subject filtering for {len(journal_candidates)} candidates.")
            journal_candidates = filter_papers_by_nature_subjects(
                journal=journal,
                candidates=journal_candidates,
                retries=retries,
                timeout_ms=timeout_ms,
            )
            log(f"{journal.short_name} kept {len(journal_candidates)} papers after Nature filtering.")
        elif journal.classification_mode == "text_rules":
            log(f"{journal.short_name} needs title/abstract rules for {len(journal_candidates)} candidates.")
            journal_candidates = filter_papers_by_text_rules(
                journal=journal,
                candidates=journal_candidates,
            )
            log(f"{journal.short_name} kept {len(journal_candidates)} papers after title/abstract filtering.")
        else:
            log(f"{journal.short_name} kept {len(journal_candidates)} papers by official section/journal scope.")

        papers.extend(journal_candidates)
        emit_progress(
            "journals",
            journal_index,
            max(total_journals, 1),
            f"{journal.short_name} 已完成，当前累计 {len(papers)} 篇",
            source=source_label,
        )

    return sorted(
        dedupe_papers(papers),
        key=lambda paper: (paper.published_date, paper.journal_short_name, paper.title),
        reverse=True,
    )


def file_tag_for_paper(paper: Paper) -> str:
    tag = re.sub(r"[^A-Za-z0-9]+", "", paper.journal_short_name)
    return tag or paper.journal_code.upper()


def download_pdf_for_paper(
    session: StealthySession,
    paper: Paper,
    *,
    output_dir: Path,
    overwrite: bool,
    retries: int,
    timeout_ms: int,
) -> Path:
    safe_title = slugify_filename(paper.title, paper.abstract_id)
    filename = f"{paper.published_date.isoformat()} - {file_tag_for_paper(paper)} - {safe_title}.pdf"
    target_path = output_dir / filename

    if target_path.exists() and not overwrite:
        log(f"Skipping existing file: {target_path.name}")
        return target_path

    for attempt in range(1, retries + 1):
        state: dict[str, object] = {"saved": False, "error": None}

        def page_action(page) -> None:
            candidate_hrefs: list[str] = []
            if paper.pdf_url:
                candidate_hrefs.append(paper.pdf_url)
            if paper.source_key == "acs" and paper.doi:
                candidate_hrefs.append(f"/doi/pdf/{paper.doi}?download=true")

            try:
                meta_pdf = page.locator('meta[name="citation_pdf_url"]').first.get_attribute("content")
            except Exception:
                meta_pdf = None
            if meta_pdf and meta_pdf not in candidate_hrefs:
                candidate_hrefs.append(meta_pdf)

            for selector in (
                'a.article__btn__secondary--pdf[href*="/doi/pdf/"]',
                'a[href*="/doi/pdf/"]',
                'a[href*="/epdf/"]',
                'a[href*="/pdf/"]',
                'a[href$=".pdf"]',
            ):
                try:
                    href = page.locator(selector).first.get_attribute("href")
                except Exception:
                    href = None
                if href and "/suppl/" not in href and href not in candidate_hrefs:
                    candidate_hrefs.append(href)

            if not candidate_hrefs:
                state["error"] = "No main PDF link found on abstract page."
                return

            errors: list[str] = []
            for href in candidate_hrefs:
                result = page.evaluate(PDF_FETCH_JS, href)
                raw = base64.b64decode(result["b64"])
                if raw.startswith(b"%PDF"):
                    target_path.write_bytes(raw)
                    state["saved"] = True
                    return
                errors.append(
                    f"Unexpected payload signature {result['headHex']} "
                    f"from {result['url']} (status {result['status']})."
                )

            state["error"] = errors[0] if errors else "No downloadable PDF payload was returned."

        try:
            fetch_with_retry(
                session,
                paper.abstract_url,
                retries=1,
                timeout_ms=timeout_ms,
                page_action=page_action,
            )
        except Exception as error:
            state["error"] = str(error)

        if state["saved"]:
            log(f"Saved {target_path.name}")
            return target_path

        if target_path.exists():
            try:
                target_path.unlink()
            except OSError:
                pass

        error_text = state["error"] or "Unknown PDF download failure."
        diagnose_possible_vpn_issue(paper.abstract_url, str(error_text))
        if attempt == retries:
            raise RuntimeError(f"{paper.title}: {error_text}")
        log(f"Retrying PDF download for '{paper.title}' after attempt {attempt}/{retries}: {error_text}")
        time.sleep(min(attempt, 3))

    raise RuntimeError(f"Unreachable download failure for {paper.title}")


def print_paper_list(papers: Iterable[Paper]) -> None:
    for index, paper in enumerate(papers, start=1):
        line = f"{index}. {paper.published_date.isoformat()} | {paper.journal_short_name} | {paper.title}"
        if paper.classification_reason:
            line += f"\n   [{paper.classification_reason}]"
        line += f"\n   {paper.abstract_url}"
        print(safe_console_text(line))


def needs_isolated_profile_retry(error: Exception) -> bool:
    message = normalize_space(str(error)).lower()
    hints = (
        "target page, context or browser has been closed",
        "opening in existing browser session",
        "user data directory is already in use",
        "processsingleton",
        "profile appears to be in use",
    )
    return any(hint in message for hint in hints)


def isolated_profile_dir(base_dir: Path, source: str) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return base_dir.parent / f"{base_dir.name}-{source.lower()}-{os.getpid()}-{stamp}"


def needs_headed_browser_retry(error: Exception) -> bool:
    message = normalize_space(str(error)).lower()
    hints = (
        "cloudflare",
        "just a moment",
        "challenge-like",
        "access denied",
        "timeout",
        "timed out",
        "wait_selector",
        "locator.bounding_box",
    )
    return any(hint in message for hint in hints)


def stealthy_session_kwargs(*, profile_dir: Path, timeout_ms: int, headless: bool) -> dict[str, object]:
    return {
        "headless": headless,
        "real_chrome": True,
        "solve_cloudflare": True,
        "block_webrtc": True,
        "hide_canvas": True,
        "google_search": True,
        "timeout": timeout_ms,
        "wait": 500,
        "user_data_dir": str(profile_dir),
    }


def run_journal_task(
    source: str,
    *,
    journal: JournalSpec,
    args: argparse.Namespace,
    cutoff_date: dt.date,
    output_dir: Path,
    user_data_dir: Path,
) -> tuple[list[Paper], list[str]]:
    source_label = source.upper()

    def execute_with_profile(profile_dir: Path, *, headless: bool) -> tuple[list[Paper], list[str]]:
        profile_dir.mkdir(parents=True, exist_ok=True)
        log(
            f"{source_label} / {journal.short_name} using browser profile: {profile_dir} "
            f"({'headless' if headless else 'headed'})"
        )
        with StealthySession(**stealthy_session_kwargs(profile_dir=profile_dir, timeout_ms=args.timeout_ms, headless=headless)) as session:
            papers = collect_recent_papers(
                session,
                journals=[journal],
                section_slug=args.section,
                cutoff_date=cutoff_date,
                max_pages=args.max_pages,
                retries=args.retries,
                timeout_ms=args.timeout_ms,
                source_label=source_label,
            )

            if args.list_only or not papers:
                return papers, []

            failures: list[str] = []
            total_papers = len(papers)
            emit_progress(
                "downloads",
                0,
                max(total_papers, 1),
                f"{source_label} / {journal.short_name} 准备下载 {total_papers} 篇",
                source=source_label,
            )
            for index, paper in enumerate(papers, start=1):
                try:
                    download_pdf_for_paper(
                        session,
                        paper,
                        output_dir=output_dir,
                        overwrite=args.overwrite,
                        retries=args.retries,
                        timeout_ms=args.timeout_ms,
                    )
                except Exception as error:  # pragma: no cover - depends on browser/network conditions
                    failures.append(f"{paper.title}: {error}")
                    log(f"Failed to download '{paper.title}': {error}")

                emit_progress(
                    "downloads",
                    index,
                    max(total_papers, 1),
                    f"{source_label} / {journal.short_name} 下载进度 {index}/{total_papers}",
                    source=source_label,
                )
        return papers, failures

    planned_attempts: list[tuple[Path, bool]] = [(user_data_dir, args.headless)]
    if args.headless:
        planned_attempts.append((user_data_dir, False))

    attempted: set[tuple[str, bool]] = set()
    last_error: Exception | None = None
    while planned_attempts:
        profile_dir, headless = planned_attempts.pop(0)
        attempt_key = (str(profile_dir), headless)
        if attempt_key in attempted:
            continue
        attempted.add(attempt_key)
        try:
            return execute_with_profile(profile_dir, headless=headless)
        except Exception as error:
            last_error = error
            if needs_isolated_profile_retry(error):
                fallback_profile_dir = isolated_profile_dir(profile_dir, f"{source}-{journal.code}")
                log(
                    f"{source_label} / {journal.short_name} detected a busy browser profile and will retry with "
                    f"isolated profile: {fallback_profile_dir}"
                )
                planned_attempts.insert(0, (fallback_profile_dir, headless))
                if headless:
                    planned_attempts.insert(1, (fallback_profile_dir, False))
                continue
            if headless and needs_headed_browser_retry(error):
                log(
                    f"{source_label} / {journal.short_name} hit a Cloudflare-like/timeout failure in headless mode. "
                    "Retrying with a headed browser."
                )
                planned_attempts.insert(0, (profile_dir, False))
                continue
            raise

    if last_error is None:
        raise RuntimeError(f"{source_label} / {journal.short_name} failed before any browser attempt was made.")
    raise last_error


def run_source(
    source: str,
    *,
    journals: list[JournalSpec],
    args: argparse.Namespace,
    cutoff_date: dt.date,
    output_dir: Path,
    user_data_dir: Path,
) -> tuple[list[Paper], list[str]]:
    source_label = source.upper()
    if args.parallel_sites and len(journals) > 1:
        papers: list[Paper] = []
        failures: list[str] = []
        total_journals = len(journals)
        emit_progress("journals", 0, max(total_journals, 1), f"准备并行扫描 {total_journals} 本期刊", source=source_label)

        futures = {}
        max_workers = min(3, total_journals)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for journal in journals:
                journal_profile_dir = user_data_dir / journal.code
                journal_profile_dir.mkdir(parents=True, exist_ok=True)
                futures[executor.submit(
                    run_journal_task,
                    source,
                    journal=journal,
                    args=args,
                    cutoff_date=cutoff_date,
                    output_dir=output_dir,
                    user_data_dir=journal_profile_dir,
                )] = journal

            for completed_count, future in enumerate(as_completed(futures), start=1):
                journal = futures[future]
                journal_papers, journal_failures = future.result()
                papers.extend(journal_papers)
                failures.extend(journal_failures)
                emit_progress(
                    "journals",
                    completed_count,
                    max(total_journals, 1),
                    f"{journal.short_name} 已完成，当前累计 {len(papers)} 篇",
                    source=source_label,
                )
                log(f"{source_label} / {journal.short_name} finished with {len(journal_papers)} matching papers.")
        return papers, failures

    def execute_with_profile(profile_dir: Path, *, headless: bool) -> tuple[list[Paper], list[str]]:
        profile_dir.mkdir(parents=True, exist_ok=True)
        log(f"{source_label} using browser profile: {profile_dir} ({'headless' if headless else 'headed'})")
        with StealthySession(**stealthy_session_kwargs(profile_dir=profile_dir, timeout_ms=args.timeout_ms, headless=headless)) as session:
            papers = collect_recent_papers(
                session,
                journals=journals,
                section_slug=args.section,
                cutoff_date=cutoff_date,
                max_pages=args.max_pages,
                retries=args.retries,
                timeout_ms=args.timeout_ms,
                source_label=source_label,
            )

            if args.list_only or not papers:
                return papers, []

            failures: list[str] = []
            total_papers = len(papers)
            emit_progress("downloads", 0, max(total_papers, 1), f"{source_label} 准备下载 {total_papers} 篇", source=source_label)
            for index, paper in enumerate(papers, start=1):
                try:
                    download_pdf_for_paper(
                        session,
                        paper,
                        output_dir=output_dir,
                        overwrite=args.overwrite,
                        retries=args.retries,
                        timeout_ms=args.timeout_ms,
                    )
                except Exception as error:  # pragma: no cover - depends on browser/network conditions
                    failures.append(f"{paper.title}: {error}")
                    log(f"Failed to download '{paper.title}': {error}")

                emit_progress(
                    "downloads",
                    index,
                    max(total_papers, 1),
                    f"{source_label} 下载进度 {index}/{total_papers}",
                    source=source_label,
                )
        return papers, failures

    planned_attempts: list[tuple[Path, bool]] = [(user_data_dir, args.headless)]
    if args.headless:
        planned_attempts.append((user_data_dir, False))

    attempted: set[tuple[str, bool]] = set()
    last_error: Exception | None = None
    while planned_attempts:
        profile_dir, headless = planned_attempts.pop(0)
        attempt_key = (str(profile_dir), headless)
        if attempt_key in attempted:
            continue
        attempted.add(attempt_key)
        try:
            return execute_with_profile(profile_dir, headless=headless)
        except Exception as error:
            last_error = error
            if needs_isolated_profile_retry(error):
                fallback_profile_dir = isolated_profile_dir(profile_dir, source)
                log(
                    f"{source_label} detected a busy browser profile and will retry with isolated profile: "
                    f"{fallback_profile_dir}"
                )
                planned_attempts.insert(0, (fallback_profile_dir, headless))
                if headless:
                    planned_attempts.insert(1, (fallback_profile_dir, False))
                continue
            if headless and needs_headed_browser_retry(error):
                log(
                    f"{source_label} hit a Cloudflare-like/timeout failure in headless mode. "
                    "Retrying with a headed browser."
                )
                planned_attempts.insert(0, (profile_dir, False))
                continue
            raise

    if last_error is None:
        raise RuntimeError(f"{source_label} failed before any browser attempt was made.")
    raise last_error


def resolve_today(value: str | None) -> dt.date:
    if value is None:
        return dt.date.today()
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def main() -> None:
    args = parse_args()
    if args.days < 1:
        fail("--days must be at least 1.")
    if args.max_pages < 1:
        fail("--max-pages must be at least 1.")
    if args.retries < 1:
        fail("--retries must be at least 1.")

    today = resolve_today(args.today)
    cutoff_date = today - dt.timedelta(days=args.days - 1)
    selected_sources = parse_sources(args.sources)
    selected_journals = journals_for_sources(selected_sources)
    if not selected_journals:
        fail("No journals matched the selected sources.")

    output_dir = args.output_dir.expanduser().resolve()
    user_data_dir = args.user_data_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    user_data_dir.mkdir(parents=True, exist_ok=True)

    log(f"Selected sources: {', '.join(source.upper() for source in selected_sources)}")
    log(f"Target journals: {', '.join(journal.short_name for journal in selected_journals)}")
    log(f"PRL section filter: {args.section}")
    log(f"Date window: {cutoff_date.isoformat()} through {today.isoformat()} (inclusive)")
    log(f"Output directory: {output_dir}")
    log(f"Browser profile directory: {user_data_dir}")
    log(f"Parallel search: {'enabled' if args.parallel_sites else 'disabled'}")
    try:
        ensure_scholarly_direct_network()
    except Exception as error:  # pragma: no cover - machine-specific proxy setup
        log(f"Warning: failed to auto-check journal direct-network settings: {error}")

    grouped_journals: dict[str, list[JournalSpec]] = {
        source: [journal for journal in selected_journals if journal.source_key.lower() == source]
        for source in selected_sources
    }

    collected_papers: list[Paper] = []
    failures: list[str] = []
    if args.parallel_sites and len(selected_sources) > 1:
        futures = {}
        with ThreadPoolExecutor(max_workers=len(selected_sources)) as executor:
            for source in selected_sources:
                source_profile_dir = user_data_dir / source
                source_profile_dir.mkdir(parents=True, exist_ok=True)
                futures[executor.submit(
                    run_source,
                    source,
                    journals=grouped_journals[source],
                    args=args,
                    cutoff_date=cutoff_date,
                    output_dir=output_dir,
                    user_data_dir=source_profile_dir,
                )] = source

            for future in as_completed(futures):
                source = futures[future]
                source_papers, source_failures = future.result()
                collected_papers.extend(source_papers)
                failures.extend(source_failures)
                log(f"{source.upper()} task finished with {len(source_papers)} matching papers.")
    else:
        for source in selected_sources:
            source_profile_dir = user_data_dir / source
            source_profile_dir.mkdir(parents=True, exist_ok=True)
            source_papers, source_failures = run_source(
                source,
                journals=grouped_journals[source],
                args=args,
                cutoff_date=cutoff_date,
                output_dir=output_dir,
                user_data_dir=source_profile_dir,
            )
            collected_papers.extend(source_papers)
            failures.extend(source_failures)

    papers = sorted(
        dedupe_papers(collected_papers),
        key=lambda paper: (paper.published_date, paper.journal_short_name, paper.title),
        reverse=True,
    )

    if not papers:
        log("No papers matched the requested date window.")
        return

    log(f"Found {len(papers)} matching condensed-matter papers.")
    print_paper_list(papers)

    if args.list_only:
        return

    if failures:
        print("\nDownload finished with failures:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        raise SystemExit(2)

    log("All matching PDFs downloaded successfully.")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    main()
