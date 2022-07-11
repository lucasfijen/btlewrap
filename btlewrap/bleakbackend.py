"""Backend for Miflora using the bluepy library."""
import re
import logging
import time
from typing import List, Tuple, Callable
from btlewrap.base import AbstractBackend, BluetoothBackendException


_LOGGER = logging.getLogger(__name__)
RETRY_LIMIT = 3
RETRY_DELAY = 0.1


def wrap_exception(func: Callable) -> Callable:
    """Decorator to wrap BTLEExceptions into BluetoothBackendException."""
    try:
        # only do the wrapping if bluepy is installed.
        # otherwise it's pointless anyway
        from bleak.exc import BleakDBusError, BleakError
    except ImportError:
        return func

    def _func_wrapper(*args, **kwargs):
        error_count = 0
        last_error = None
        while error_count < RETRY_LIMIT:
            try:
                return func(*args, **kwargs)
            except (BleakDBusError, BleakError) as exception:
                error_count += 1
                last_error = exception
                time.sleep(RETRY_DELAY)
                _LOGGER.debug(
                    "Call to %s failed, try %d of %d", func, error_count, RETRY_LIMIT
                )
        raise BluetoothBackendException() from last_error

    return _func_wrapper


class BleakBackend(AbstractBackend):
    """Backend for Miflora using the bleak library."""

    def __init__(self, adapter: str = "hci0", address_type: str = "public"):
        """Create new instance of the backend."""
        super(BleakBackend, self).__init__(adapter, address_type)
        self._peripheral = None

    @wrap_exception
    async def connect(self, mac: str):
        """Connect to a device."""
        from bleak import BleakClient
        # from bluepy.btle import Peripheral
            
        self._peripheral = await BleakClient(mac).connect()
        # self._peripheral = Peripheral(mac, iface=iface, addrType=self.address_type)

    @wrap_exception
    async def disconnect(self):
        """Disconnect from a device if connected."""
        if self._peripheral is None:
            return
    
        await self._peripheral.disconnect()
        self._peripheral = None

    @wrap_exception
    async def read_handle(self, handle: int) -> bytes:
        """Read a handle from the device.

        You must be connected to do this.
        """
        if self._peripheral is None:
            raise BluetoothBackendException("not connected to backend")

        #TODO: Seems like we need a -1 for the handle value, whereas miflora integration seems to use the char value handle, which is +1 from the hexa of the handle itself.
        return await self._peripheral.read_gatt_char(handle - 1)

    @wrap_exception
    async def write_handle(self, handle: int, value: bytes):
        """Write a handle from the device.

        You must be connected to do this.
        """
        if self._peripheral is None:
            raise BluetoothBackendException("not connected to backend")
        return await self._peripheral.write_gatt_char(handle - 1, value, True)

    @wrap_exception
    async def wait_for_notification(self, handle: int, delegate, notification_timeout: float):
        if self._peripheral is None:
            raise BluetoothBackendException("not connected to backend")

        #TODO: Need to think of something to handle this
        self.write_handle(handle, self._DATA_MODE_LISTEN)
        self._peripheral.withDelegate(delegate)
        return self._peripheral.waitForNotifications(notification_timeout)

    @staticmethod
    async def supports_scanning() -> bool:
        return True

    @staticmethod
    async def check_backend() -> bool:
        """Check if the backend is available."""
        try:
            from bleak import BleakClient # noqa: F401 #pylint: disable=unused-import

            return True
        except ImportError as importerror:
            _LOGGER.error("bleak not found: %s", str(importerror))
        return False


    @staticmethod
    @wrap_exception
    async def scan_for_devices(timeout: float, adapter="hci0") -> List[Tuple[str, str]]:
        """Scan for bluetooth low energy devices.

        Note this must be run as root!"""
        from bleak import BleakScanner
        
        scanner = BleakScanner()
        result = []
        for device in await scanner.discover(timeout):
            result.append((device.address, device.name))
        return result
