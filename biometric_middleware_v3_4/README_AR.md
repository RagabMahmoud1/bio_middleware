# Odoo Biometric Middleware v2

النسخة الثانية مخصصة لحل مشكلة كمية البيانات الكبيرة على ZKTeco.

## الجديد
- Bulk Insert إلى SQLite.
- فلترة بالتاريخ بعد استلام سجلات ZKTeco.
- فلترة Employee ID اختيارية.
- اختبار كل جهاز منفصل.
- Device Sync State.
- قياس واضح لزمن قراءة ZKTeco وعدد السجلات.

## مهم
في `pyzk`، `get_attendance()` قد يقرأ قائمة السجلات كاملة من الجهاز قبل أن نتمكن من تطبيق Date/User Filter.
لذلك الفلترة هنا تقلل التخزين والمعالجة بشكل كبير، لكنها لا تجعل جهاز ZKTeco نفسه ينفذ SQL-like date filter.

## أول اختبار
1. فك الضغط.
2. شغّل `install.ps1`.
3. عدّل `config.yaml` إذا احتجت.
4. اختبار الاتصال:
   `.\device_test.ps1 zk_room_1`
5. قراءة ZKTeco بتاريخ قريب:
   `.
un_device_once.ps1 zk_room_1 "2026-08-26 00:00:00"`
6. بعد انتهائه:
   `.\show_status.ps1`

لا تشغّل Windows Service الآن.


## تحديث v2.1 - Hikvision

تم تعديل Hikvision Adapter بناءً على الاختبار الفعلي للجهاز DS-K1T502DBFWX-C:

- استخدام `major: 5` لأحداث Access Control.
- استخدام Session واحدة مع HTTP Digest Authentication.
- إضافة Timezone `+03:00`.
- إضافة Pagination تلقائية عند `responseStatusStrg = MORE`.
- تجاهل Door/Alarm events التي لا تحتوي Employee/User ID.
- استخدام `serialNo` كجزء من مفتاح منع التكرار.

لا تحتاج لإعادة تثبيت Python packages عند الترقية من v2 إلى v2.1.
