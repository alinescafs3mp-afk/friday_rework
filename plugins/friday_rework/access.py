"""Product link/role metadata in the existing native plugin store."""
import copy
from .associations import Associations, _sync_directory
from hermes_cli.friday_product_access import (
    KEY, access_policy, current_access, principal_id, validate_access,
)


class ProductAccess:
    def __init__(self, state):
        self.state = state
        self.store = Associations(state)

    def users(self):
        return copy.deepcopy(current_access(self.state)["users"])

    def set_user(self, *, platform, transport_profile, account_id, user_id, enabled, role):
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
            document = current_access(self.state)
            document["users"][key] = row
            validate_access(document)
            self.store.state_set(KEY, document)
            _sync_directory(self.state.data_dir)
            if current_access(self.state)["users"].get(key) != row:
                raise RuntimeError("product_access_write_unconfirmed")
        return {"principal_id": key, **row}
