"""Product link/role metadata in the existing native plugin store."""
import copy
from .associations import Associations, _sync_directory
from hermes_cli.friday_product_access import (
    KEY, access_policy, current_access, principal_id, validate_access,
)


class ProductAccess:
    def __init__(self, state, *, _operator=None):
        self.state = state
        self.store = Associations(state, _operator=_operator)

    def _document(self):
        if self.store._operator is not None:
            self.store._operator.check(self.state)
            return validate_access(self.store.state_get(KEY, {"schema": KEY, "users": {}}))
        return current_access(self.state)

    @staticmethod
    def require_transport(transport_profile):
        from hermes_constants import get_hermes_home
        from hermes_cli.profiles import get_profile_dir
        if get_hermes_home().resolve() != get_profile_dir(transport_profile).resolve():
            raise PermissionError("receiving_transport_authority_required")

    def users(self):
        rows = self._document()["users"]
        for row in rows.values():
            self.require_transport(row["transport_profile"])
        return copy.deepcopy(rows)

    def set_user(self, *, platform, transport_profile, account_id, user_id, enabled, role):
        if self.store._operator is not None:
            self.store._operator.require_write()
        self.require_transport(transport_profile)
        policy = access_policy()
        if policy is None or not any(
            (a["platform"], a["transport_profile"], a["account_id"]) == (platform, transport_profile, account_id)
            for a in policy["accounts"]
        ):
            raise ValueError("foreign_product_account")
        key = principal_id(platform, transport_profile, account_id, user_id)
        row = dict(platform=platform, transport_profile=transport_profile, account_id=account_id,
                   user_id=user_id, enabled=enabled, role=role)
        validate_access({"schema": KEY, "users": {key: row}})
        with self.store._locked():
            return self._write_user_locked(key, row)

    def _write_user_locked(self, key, row):
        """Compound administrative setup already holds this exact store lock."""
        if self.store._operator is not None:
            self.store._operator.require_write()
        validate_access({"schema": KEY, "users": {key: row}})
        document = self._document()
        document["users"][key] = row
        validate_access(document)
        self.store.state_set(KEY, document)
        if self.store._operator is not None:
            self.store._check_local_state()
        _sync_directory(self.state.data_dir)
        confirmed = self._document()["users"].get(key)
        if not confirmed or any(confirmed.get(k) != v for k, v in row.items()):
            raise RuntimeError("product_access_write_unconfirmed")
        return {"principal_id": key, **confirmed}
