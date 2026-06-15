import logging
import os
import re

from dotenv import load_dotenv


logger = logging.getLogger(__name__)


class ConfigLoader:
    def __init__(self, config_dir="config"):
        self.config_dir = config_dir
        self.env_path = os.path.join(self.config_dir, ".env")
        load_dotenv(self.env_path)

    def get_env_var(self, var_name, default=None):
        return os.getenv(var_name, default)

    def load_connections(self, connections_file=None):
        """
        Load Oracle connection profiles from a text file.
        Expected format:
        ## PROFILE_NAME
        USER = username
        PASSWORD = password
        DSN = host:port/service_name
        """
        if not connections_file:
            connections_file = self.get_env_var(
                "CONNECTIONS_FILE", os.path.join(self.config_dir, "Cadena_conexions.txt")
            )

        profiles = {}
        current_profile = None

        if not os.path.exists(connections_file):
            return profiles

        with open(connections_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or (line.startswith("#") and not line.startswith("##")):
                    continue

                profile_match = re.match(r"^##\s*(.+)$", line)
                if profile_match:
                    current_profile = profile_match.group(1).strip()
                    profiles[current_profile] = {}
                    continue

                if current_profile and "=" in line:
                    key, val = line.split("=", 1)
                    profiles[current_profile][key.strip().upper()] = val.strip()

        return profiles

    @staticmethod
    def _normalize_profile_name(name):
        if not name:
            return ""
        cleaned = str(name).strip().strip("'\"`")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.casefold()

    def _resolve_existing_profile_key(self, profile_name, profiles):
        normalized = self._normalize_profile_name(profile_name)
        if not normalized:
            return None
        for existing_name in profiles.keys():
            if self._normalize_profile_name(existing_name) == normalized:
                return existing_name
        return None

    @staticmethod
    def _serialize_profiles(profiles):
        blocks = []
        for profile_name, values in profiles.items():
            blocks.append(
                "\n".join(
                    [
                        f"## {profile_name}",
                        f"USER = {values.get('USER', '')}",
                        f"PASSWORD = {values.get('PASSWORD', '')}",
                        f"DSN = {values.get('DSN', '')}",
                    ]
                )
            )
        if not blocks:
            return ""
        return "\n\n".join(blocks) + "\n"

    def resolve_profile_name(self, profile_name=None, profiles=None):
        """Resolve profile names with tolerance for case, spaces and extra text."""
        if profiles is None:
            profiles = self.load_connections()
        if not profiles:
            return None

        if not profile_name:
            profile_name = self.get_env_var("DEFAULT_PROFILE")
        if not profile_name:
            return None

        requested_raw = str(profile_name).strip()
        if requested_raw in profiles:
            return requested_raw

        requested = self._normalize_profile_name(requested_raw)
        if not requested:
            return None

        normalized_map = {self._normalize_profile_name(k): k for k in profiles.keys()}
        if requested in normalized_map:
            return normalized_map[requested]

        requested_tokens = set(re.findall(r"[a-z0-9]+", requested))
        best_key = None
        best_score = (-1, -1)

        for key in profiles.keys():
            key_norm = self._normalize_profile_name(key)
            if not key_norm:
                continue

            if key_norm in requested:
                score = (3, len(key_norm))
            elif requested in key_norm:
                score = (2, len(key_norm))
            else:
                key_tokens = set(re.findall(r"[a-z0-9]+", key_norm))
                if not key_tokens:
                    continue
                overlap = len(requested_tokens & key_tokens)
                if overlap == 0:
                    continue
                subset_bonus = 1 if key_tokens.issubset(requested_tokens) else 0
                score = (subset_bonus, overlap * 100 + len(key_norm))

            if score > best_score:
                best_score = score
                best_key = key

        return best_key

    def get_profile(self, profile_name=None):
        """Return credentials for a profile merged with global env config."""
        profiles = self.load_connections()
        resolved_profile = self.resolve_profile_name(profile_name, profiles)
        profile = profiles.get(resolved_profile) if resolved_profile else None

        if profile:
            profile = dict(profile)
            profile["PROFILE_NAME"] = resolved_profile
            profile["ORACLE_CLIENT_LIB_DIR"] = self.get_env_var("ORACLE_CLIENT_LIB_DIR")

        return profile

    def save_connection(self, profile_name, user, password, dsn):
        """Save or update a connection profile into Cadena_conexions.txt."""
        connections_file = self.get_env_var(
            "CONNECTIONS_FILE", os.path.join(self.config_dir, "Cadena_conexions.txt")
        )

        os.makedirs(os.path.dirname(connections_file), exist_ok=True)

        normalized_name = str(profile_name or "").strip()
        if not normalized_name:
            logger.error("No es pot desar la connexio: profile_name buit")
            return False

        try:
            profiles = self.load_connections(connections_file)
            existing_key = self._resolve_existing_profile_key(normalized_name, profiles)
            target_key = existing_key or normalized_name
            profiles[target_key] = {
                "USER": str(user or "").strip(),
                "PASSWORD": str(password or "").strip(),
                "DSN": str(dsn or "").strip(),
            }
            with open(connections_file, "w", encoding="utf-8") as f:
                f.write(self._serialize_profiles(profiles))
            return True
        except OSError:
            logger.exception("Error desant connexio a %s", connections_file)
            return False

    def save_env_var(self, var_name, value):
        """Update or append an env variable in config/.env."""
        lines = []
        found = False
        if os.path.exists(self.env_path):
            with open(self.env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        new_lines = []
        for line in lines:
            if line.startswith(f"{var_name}="):
                new_lines.append(f"{var_name}={value}\n")
                found = True
            else:
                new_lines.append(line)

        if not found:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines[-1] += "\n"
            new_lines.append(f"{var_name}={value}\n")

        try:
            with open(self.env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            load_dotenv(self.env_path, override=True)
            return True
        except OSError:
            logger.exception("Error desant .env a %s", self.env_path)
            return False
