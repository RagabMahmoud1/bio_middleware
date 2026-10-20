<div dir="rtl" align="right">

# خطة تجهيز ERP Test منفصلًا وتجربة التسليم إلى ERP وRSH

**التاريخ:** 2026-10-20
**المرجع:** feature/biometric-multi-target
**النطاق:** قواعد Test فقط. يُحظر تغيير أي Production Service أو Live DB أو جهاز حقيقي.

## الوضع المثبت

- `/etc/odoo-test.conf` يربط الخدمة الموجودة على 8070 بقاعدة `test_RSH` فقط. **ممنوع إعادة توظيفها للقاعدة `test`.**
- موديولا البصمة موجودان تحت `/odoo16/custom/test`، ولكنهما غير مثبتين في ERP Test `test` حسب SQL السابق.
- RSH Test لديها E2E مستقل ناجح، ولا حاجة لإعادته.
- اتصال `rajab_work` المتاح حاليًا يوجّه أوامر SSH إلى جهاز التطوير `ragab` ولا يوفر حتى الآن جلسة على Linux Server `vmi1260282`؛ لذلك لم تُنفذ التهيئة الفعلية على السيرفر في جلسة المتابعة الحالية.

## المرحلة 1 — فحص قراءة فقط

الأداة الجديدة `scripts/audit_dual_odoo_test_readonly.py` تستخدم أوامر قراءة فقط وتُخرج JSON بلا كلمات مرور أو API Tokens أو بيانات موظفين. على سيرفر أودو يُشغّل:

```bash
python3 scripts/audit_dual_odoo_test_readonly.py
```

يُراجع تحديدًا:
- حالة وحدات Odoo ومنافذ TCP المستمعة.
- المفاتيح المسموحة فقط من `/etc/odoo-test.conf` و`/etc/odoo16-server.conf` وإعداد ERP Test الجديد إن وجد.
- أن موديولي البصمة يمكن العثور عليهما بالفعل عبر addons_path الصحيح.
- حالات وترقيم `hr_attendance` و`rm_hr_attendance_sheet` وموديولي البصمة لكل قاعدة.
- لا تُعتبر نتيجة تشغيل الأداة على جهاز التطوير المحلي دليلًا على إعدادات سيرفر العميل.

**شرط التوقف:** أي Config غير مقروء، أو عدم توفر SQL read-only، أو تضارب Port/Service: لا متابعة للتثبيت قبل معرفة السبب.

## المرحلة 2 — إعداد خدمة ERP Test فقط

1. بعد تدقيق المنافذ، اختَر منفذًا غير مستخدم. `8081` مجرد مرشح، **وليس منفذًا محجوزًا أو تم إثبات خلوّه على سيرفر العميل**.
2. خذ Backup من قاعدة `test` وFilestore الخاص بها، واختبر صلاحية النسخة وسيناريو الاستعادة المعزولة قبل تغيير Schema.
3. جهّز ملف Config منفصل `/etc/odoo-erp-test.conf` وملف خدمة منفصلًا `odoo-erp-test.service`، مع `User=odoo16` و`addons_path` خاص بالكود التجريبي. لا تغير `/etc/odoo-test.conf` أو خدمة الإنتاج.
4. الضبط اللازم قبل أول Install هو:

```ini
[options]
addons_path = /odoo16/odoo16-server/addons,/odoo16/custom/test
db_name = test
dbfilter = ^test$
http_interface = 127.0.0.1
http_port = 8081
max_cron_threads = 0
list_db = False
```

هذا **قالب إيضاح** وليس ملف خدمة صالحًا للتشغيل دون مراجعة معاملات PostgreSQL وOdoo وسجل الخدمة وأذونات الملفات المتوافقة مع البيئة الفعلية.

5. تحقّق أن الأمر الذي سيُشغل Odoo يستخدم هذا الـConfig فقط، ولا يحمل أية قاعدة إنتاج ضمن `db_name`؛ ثم ثبّت على `test` فقط بالترتيب:
   - `rgb_biometric_attendance_bridge` الذي يعتمد على `hr_attendance`.
   - `rgb_biometric_first_last_attendance` الذي يعتمد أيضًا على `rm_hr_attendance_sheet`.
6. ابدأ ERP Test بمهمة Cron معطلة في هذه الخدمة، وتحقق أن `/biometric/api/v1/allowed-employees` يرتبط بقاعدة `test` وليس أي Production DB. إتاحة HTTP أوليًا على loopback فقط؛ لا تفتح 8081 للإنترنت.

**شرط التوقف:** عدم ضمان استقلال الخدمة أو تركيب الموديولين على قاعدة `test` بالاسم الصحيح يعني NO-GO لاختبار HTTP.

## المرحلة 3 — بيانات صناعية على Test فقط

بعد التأكد من Backup Test والموديولات وشركة ERP الصحيحة، شغّل `scripts/bootstrap_dual_target_tests.py` **مرة واحدة** داخل Odoo Shell لكل DB، بعد التأكد أن `env.cr.dbname` يطابق `test` أو `test_RSH` وأن المستخدم يمتلك صلاحيات الاختبار. الأداة تفشل لو وجدت علامات التشغيل السابق.

هي تنشئ أجهزة وأكواد اصطناعية محجوزة فقط، ولا تغير أجهزة `zk_room_1/hik_room_2` أو Mappings الخاصة بالموظفين. في قاعدة Test فقط قد تعطل Cron اليومي لضمان اختبار حتمي؛ يجب تسجيل الحالة السابقة قبل التشغيل وإعادتها لاحقًا بعد اعتماد اختبار Cron مستقل.

## المرحلة 4 — REAL HTTP Middleware على القاعدتين

بعد تهيئة القاعدتين ووجود ملفات Token السرية بصلاحية 0600:

```bash
python3 scripts/run_dual_target_http_synthetic_e2e.py
```

حواجز الأمان:
- يتحقق من Config و`dbfilter` و`db_name` لكل Test service، ومن فصل المنافذ والأسرار.
- لا يستدعي الأجهزة الحقيقية ولا URL أي Production.
- يتحقق من قوائم السماح الصناعية قبل أول POST.
- يستخدم SQLite مؤقتة ومنفصلة عن Windows Runtime؛ يرسل 4 أحداث اصطناعية مجموعها 3 لكل DB.
- يحاكي انقطاع RSH بواسطة اتصال loopback غير مستمع دون إيقاف RSH Test، ويؤكد احتفاظ ERP بحالات ACK.
- يعيد فتح SQLite ويستكمل RSH، ويمتحن عدم Replay إلى ERP وتكرار إرسال الحدث.
- يتحقق بعد كل مرحلة من Raw Event counts عبر PostgreSQL read-only.
- إذا كانت مفاتيح هذا الاختبار موجودة في أي DB Test سابقًا، يرفض التكرار تمامًا.

بعد نجاح HTTP، تُشغّل أداة `scripts/verify_dual_target_http_attendance.py` **من داخل Odoo Shell على كل Test DB على حدة**. وهي تختار 3 Raw Events صناعية بالمفاتيح الثابتة وتعالجها دون تشغيل Global Cron؛ تثبت حضورًا واحدًا من بصمتي جهازين، وخطأ البصمة المنفردة بدون Attendance، وعدم التكرار عند إعادة المعالجة.

**مهم:** هاتان الأداتان جاهزتان للتنفيذ لكن لم تُنفذا على سيرفر العميل بعد. اختبارات الكود المحلية ليست إثبات HTTP.

## المرحلة 5 — قبل Production

لا Go-Live دون Evidence مباشر لكل مما يلي: Backups + Restore Drill لقاعدتي Odoo وFilestore وSQLite Windows، RSH Live Mapping معتمد من HR والهوية الرسمية، اختبار Cron فعلي وتقييم أثر 54 مهمة متأخرة على HR/Accounting/EDI، تحديد `start_at` بدقة، إقرار عدم ERP Replay، نافذة صيانة، وخطة Rollback بإقرار المسؤولين.

</div>
