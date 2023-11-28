#!/usr/bin/env python3

import sys, argparse, zlib

def desc():
    return("""
TLSR8 OTA image extractor for Multi-address startup mode
Given a dump of chip's flash memory this tool extracts
both images (active and backup) into separate files.
Found images will be named <flash_dump>-<generated_suffix>.bin
    """)

def extract_image(offset, raw):
    # tl_zigbee_sdk/zigbee/ota/ota.c ota_newImageValid
    start_flag = int.from_bytes(raw[0x08:0x0c], byteorder='little')
    if (start_flag & 0xffffff00) != 0x544c4e00:
        print("Image at offset 0x%06X, has invalid StartFlag 0x%08X (is must be 0x544c4e**), skipping" % (offset, start_flag))
        return None

    size = int.from_bytes(raw[0x18:0x1c], byteorder='little')
    # base image
    image = raw[0:size - 4]

    # Restore OTA_MAGIC (just in case this image was written not over the air)
    image[0x06:0x08] = b'\x5d\x02'
    # Restore TL_IMAGE_START_FLAG (see function mcuBootAddrGet in tl_zigbee_sdk/zigbee/ota/ota.c)
    image[0x08] = 0x4b
    # Just in case there are more modifications in the file header, not only StartFlag.
    # Image may still work but CRC needs to be re-calculated
    crc = zlib.crc32(image) ^ 0xffffffff
    crc0 = int.from_bytes(raw[size-4:size], byteorder='little')
    image += crc.to_bytes(4, byteorder='little')
    if crc0 != crc:
        print("Changed CRC @%08X %08X -> %08X" % (offset+size-4, crc0, crc))
    return (image, crc0 == crc)

def find_and_store_image(path0, offset, raw, tag, is_active):
    extresult = extract_image(offset, raw[offset:])
    if not extresult:
        return None
    (img, crc_ok) = extresult

    if is_active:
        active_tag = 'Act'
    else:
        active_tag = 'Bkp'

    bad_crc_suffix = ''
    if not crc_ok:
        bad_crc_suffix = '.BAD_CRC'

    manufacturer_code   = int.from_bytes(img[0x12:0x14], byteorder='little')
    image_type          = int.from_bytes(img[0x14:0x16], byteorder='little')
    file_version        = int.from_bytes(img[0x02:0x06], byteorder='little')

    out_path = '{}-{}-{}-{:04x}-{:04x}-{:08x}.bin{}'.format(
        path0,
        tag,
        active_tag,
        manufacturer_code,
        image_type,
        file_version,
        bad_crc_suffix)

    print("image size %d 0x%06X -> %s" % (len(img), len(img), out_path))
    with open(out_path, 'wb') as f:
        f.write(img)

def main(args):
    path0 = args.flash_dump
    with open(path0, 'rb') as f:
        flashdump = bytearray(f.read(-1))

    # tl_zigbee_sdk/zigbee/ota/ota.c mcuBootAddrGet
    # FLASH_TLNK_FLAG_OFFSET    = 8
    # TL_IMAGE_START_FLAG       = 0x4b
    active_0 = flashdump[0x08] == 0x4b

    # From Application Note Telink Zigbee SDK Developer Manual, 2.4 Operation mode
    # Multi-address startup mode: image can only be located at address 0x0 or 0x40000
    find_and_store_image(path0, 0x00000, flashdump, '0', active_0)
    find_and_store_image(path0, 0x40000, flashdump, '1', not active_0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = desc(), formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("flash_dump", help="path to a raw dump of TLSR chip flash memory")
    args = parser.parse_args()

    sys.exit(main(args))

